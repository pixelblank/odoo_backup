import os
import datetime
import logging
#import subprocess
import socket # Déjà présent pour SFTP, utile pour FTP aussi
import ftplib # NOUVEL IMPORT pour FTP
import dropbox
import time
from odoo.service import db as dbservice
from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class BackupConfiguration(models.Model):
    _name = 'server.backup.config'
    _description = 'Configuration des sauvegardes'

    name = fields.Char(string='Nom', required=True)
    active = fields.Boolean(string='Actif', default=True)

    # Paramètres de sauvegarde
    backup_dir = fields.Char(
        string='Répertoire de sauvegarde',
        required=True,
        default='/var/lib/odoo/backups',
        help='Chemin absolu du répertoire où seront stockées les sauvegardes'
    )
    backup_format = fields.Selection([
        ('zip', 'ZIP (Complet: SQL + Filestore)'),  # Modifiez le label
        # ('sql', 'SQL (non compressé)'), # Optionnellement
    ], string='Format de sauvegarde', default='zip', required=True)

    # Paramètres de rétention
    days_to_keep = fields.Integer(
        string='Jours de conservation',
        required=True,
        default=7,
        help='Nombre de jours pendant lesquels conserver les sauvegardes'
    )
    max_backup_count = fields.Integer(
        string='Nombre maximum',
        required=True,
        default=5,
        help='Nombre maximum de sauvegardes à conserver'
    )

    # Paramètres de planification
    auto_backup = fields.Boolean(string='Sauvegarde automatique', default=True)
    backup_interval = fields.Selection([
        ('minutes', 'Minutes'),
        ('hours', 'Heures'),
        ('days', 'Jours'),
        ('weeks', 'Semaines'),
    ], string='Intervalle', default='days', required=True)
    backup_interval_number = fields.Integer(
        string='Fréquence',
        required=True,
        default=1
    )
    next_backup = fields.Datetime(string='Prochaine sauvegarde', compute='_compute_next_backup', store=True)

    backup_count = fields.Integer(string='Nombre de sauvegardes', compute='_compute_backup_count')
    last_backup = fields.Datetime(string='Dernière sauvegarde', compute='_compute_last_backup', store=True)

    # == Champs pour l'Export Distant ==
    export_enabled = fields.Boolean(string='Activer l\'export distant')
    export_type = fields.Selection([
        ('sftp', 'SFTP'),
        ('ftp', 'FTP'),
        ('dropbox', 'Dropbox'),
    ], string='Type d\'export', default='sftp')

    # Champs SFTP
    sftp_host = fields.Char(string='Hôte SFTP')
    sftp_port = fields.Integer(string='Port SFTP', default=22)
    sftp_user = fields.Char(string='Utilisateur SFTP')
    sftp_password = fields.Char(string='Mot de passe SFTP', help="Laissez vide si vous utilisez une clé SSH.")
    sftp_private_key = fields.Text(string='Clé privée SSH',
                                   help="Contenu de votre clé privée (ex: id_rsa). Nécessaire si pas de mot de passe.")
    sftp_remote_dir = fields.Char(string='Répertoire distant SFTP', default='/backup/',
                                  help="Chemin absolu sur le serveur SFTP où stocker les sauvegardes.")
    sftp_connection_status = fields.Selection([
        ('not_tested', 'Non testé'),
        ('success', 'Succès'),
        ('failed', 'Échec'),
    ], string='État de la connexion SFTP', default='not_tested', readonly=True, copy=False)
    sftp_last_test_message = fields.Text(string='Message du dernier test SFTP', readonly=True, copy=False)

    # Champs FTP
    ftp_host = fields.Char(string='Hôte FTP')
    ftp_port = fields.Integer(string='Port FTP', default=21)
    ftp_user = fields.Char(string='Utilisateur FTP')
    ftp_password = fields.Char(string='Mot de passe FTP')
    ftp_remote_dir = fields.Char(string='Répertoire distant FTP', default='/backup/',
                                 help="Chemin sur le serveur FTP où stocker les sauvegardes.")
    ftp_use_passive_mode = fields.Boolean(string='Utiliser le mode passif (PASV)', default=True,
                                          help="Recommandé pour la plupart des configurations réseau/pare-feu.")
    ftp_connection_status = fields.Selection([
        ('not_tested', 'Non testé'), ('success', 'Succès'), ('failed', 'Échec'),
    ], string='État de la connexion FTP', default='not_tested', readonly=True, copy=False)
    ftp_last_test_message = fields.Text(string='Message du dernier test FTP', readonly=True, copy=False)
    ftp_require_tls = fields.Boolean(
        string='Forcer TLS (FTPS/FTPES)',
        default=False,
        # Par défaut, on essaiera de se connecter et si le serveur exige TLS (comme le 530), on l'activera.
        # Mettre à True si on sait que le serveur l'exige toujours et qu'on veut être explicite.
        help="Cochez si votre serveur FTP exige explicitement TLS (FTPS/FTPES) pour les connexions."
    )
    # Dropbox
    dropbox_access_token = fields.Char(string='Token d\'accès Dropbox', password=True,
                                       help="Token d'accès généré depuis la console développeur Dropbox.")
    dropbox_remote_folder = fields.Char(string='Dossier distant Dropbox', default='/OdooBackups/',
                                        help="Chemin du dossier dans Dropbox où stocker les sauvegardes (ex: /MesSauvegardesOdoo/). Doit commencer et se terminer par un '/'. Si vous utilisez un type d'application 'App folder', ce chemin est relatif à ce dossier d'application.")
    dropbox_connection_status = fields.Selection([
        ('not_tested', 'Non testé'),
        ('success', 'Succès'),
        ('failed', 'Échec'),
    ], string='État de la connexion Dropbox', default='not_tested', readonly=True, copy=False)
    dropbox_last_test_message = fields.Text(string='Message du dernier test Dropbox', readonly=True, copy=False)
    dropbox_app_key = fields.Char(
        string='Dropbox App Key',
        help="Votre 'App key' obtenue depuis la console développeur Dropbox."
    )
    dropbox_app_secret = fields.Char(
        string='Dropbox App Secret',
        password=True,  # Pour masquer la saisie
        help="Votre 'App secret' obtenue depuis la console développeur Dropbox."
    )
    dropbox_refresh_token = fields.Char(
        string='Dropbox Refresh Token',
        password=True,  # Pour masquer la saisie
        help="Le Refresh Token à longue durée obtenu via le processus OAuth2 initial."
    )
    # Champs pour stocker l'access token actuel et son expiration (gérés par le code)
    dropbox_current_access_token = fields.Char(string='Dropbox Current Access Token', readonly=True, copy=False,
                                               groups="base.group_system")
    dropbox_access_token_expires_at = fields.Datetime(string='Access Token Expires At', readonly=True, copy=False,
                                                      groups="base.group_system")
    @api.model
    def default_get(self, fields_list):
        res = super(BackupConfiguration, self).default_get(fields_list)
        # Essayer de créer le répertoire de sauvegarde par défaut si nécessaire
        default_dir = '/var/lib/odoo/backups'
        if not os.path.exists(default_dir):
            try:
                os.makedirs(default_dir, exist_ok=True)
            except Exception as e:
                _logger.warning(f"Impossible de créer le répertoire par défaut {default_dir}: {e}")
        return res

    @api.depends('backup_interval', 'backup_interval_number', 'last_backup', 'auto_backup', 'create_date')
    def _compute_next_backup(self):
        for record in self:
            if not record.auto_backup:  # Si pas de sauvegarde auto, pas de prochaine sauvegarde planifiée
                record.next_backup = False
                continue

            last_successful_backup = self.env['server.backup.history'].search([
                ('config_id', '=', record.id),
                ('state', '=', 'done')
            ], order='create_date desc', limit=1)

            if last_successful_backup:
                base_time = last_successful_backup.create_date
            elif record.create_date:  # Si jamais de backup mais la config existe
                base_time = record.create_date  # On pourrait aussi prendre datetime.datetime.now()
                # mais create_date est plus stable pour un calcul initial
            else:  # Cas d'un record en cours de création, non encore sauvegardé
                base_time = datetime.datetime.now()  # Pour les nouveaux enregistrements non sauvegardés

                # Assurer que backup_interval_number a une valeur > 0 pour éviter des erreurs
            interval_number = record.backup_interval_number
            if interval_number <= 0:
                # Si la fréquence est 0 ou négative, on ne peut pas calculer une prochaine sauvegarde sensée
                # On pourrait soit la mettre à False, soit la mettre loin dans le futur, soit logguer une erreur.
                # Pour l'instant, si c'est 0 ou moins, on ne définit pas de prochaine sauvegarde.
                _logger.warning(f"La fréquence de l'intervalle pour '{record.name}' est {interval_number}, "
                                f"ce qui n'est pas valide pour la planification. Prochaine sauvegarde non définie.")
                record.next_backup = False
                continue

            if record.backup_interval == 'minutes':  # <--- GÉRER LE NOUVEL INTERVALLE
                next_time = base_time + datetime.timedelta(minutes=interval_number)
            elif record.backup_interval == 'hours':
                next_time = base_time + datetime.timedelta(hours=interval_number)
            elif record.backup_interval == 'days':
                next_time = base_time + datetime.timedelta(days=interval_number)
            elif record.backup_interval == 'weeks':
                next_time = base_time + datetime.timedelta(weeks=interval_number)
            else:
                _logger.warning(
                    f"Intervalle de sauvegarde inconnu '{record.backup_interval}' pour la config {record.name}. Prochaine sauvegarde non définie.")
                record.next_backup = False  # Ou un fallback
                continue

            record.next_backup = next_time

    def _compute_backup_count(self):
        for record in self:
            record.backup_count = self.env['server.backup.history'].search_count([
                ('config_id', '=', record.id)
            ])

    def _compute_last_backup(self):
        for record in self:
            last_backup = self.env['server.backup.history'].search([
                ('config_id', '=', record.id),
                ('state', '=', 'done')
            ], order='create_date desc', limit=1)
            record.last_backup = last_backup.create_date if last_backup else False

    def action_backup_now(self):
        """Lance manuellement une sauvegarde"""
        self.ensure_one()
        return self._backup_database()


    def _backup_database(self):
        """Fonction principale pour sauvegarder la base de données"""
        self.ensure_one()

        db_name = self.env.cr.dbname
        backup_dir = self.backup_dir

        # Vérifier que le répertoire existe
        if not os.path.isdir(backup_dir):
            try:
                os.makedirs(backup_dir, exist_ok=True)
            except Exception as e:
                raise UserError(_(f"Répertoire de sauvegarde '{backup_dir}' inaccessible: {e}"))

        timestamp = datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        # Le format de sauvegarde d'Odoo est toujours .zip pour un dump complet
        backup_filename = f"{db_name}_{timestamp}.zip"
        backup_file_path = os.path.join(backup_dir, backup_filename)

        history_vals = {
            'name': backup_filename,  # Nom complet avec .zip
            'config_id': self.id,
            'db_name': db_name,
            'state': 'running',
            'export_status': 'pending' if self.export_enabled else 'not_applicable',
        }
        history = self.env['server.backup.history'].create(history_vals)

        try:
            _logger.info(
                f"Lancement de la sauvegarde complète (SQL + Filestore) de '{db_name}' vers '{backup_file_path}'.")

            # Utilisation de la fonction Odoo pour un dump complet
            # dbservice.dump_db(db_name, stream_to_write_to, backup_format='zip')
            # stream_to_write_to doit être un objet fichier ouvert en mode binaire ('wb')
            with open(backup_file_path, 'wb') as backup_stream:
                dbservice.dump_db(db_name, backup_stream, backup_format='zip')  # Toujours 'zip' pour SQL+filestore

            _logger.info(f"Sauvegarde complète Odoo réussie : {backup_file_path}")

            if not os.path.exists(backup_file_path):
                raise Exception(f"Le fichier de sauvegarde {backup_file_path} n'a pas été créé.")

            file_size = os.path.getsize(backup_file_path)
            history_update_vals = {
                'state': 'done',
                'file_path': backup_file_path,
                'file_size': file_size,
                'message': f"Sauvegarde complète (SQL+Filestore) locale réussie. Taille: {file_size} octets."
            }
            history.write(history_update_vals)

            _logger.info(f"Sauvegarde locale réussie : {backup_file_path} (Taille: {file_size} octets)")

            self._clean_old_backups()

            export_message_suffix = ""
            if self.export_enabled and backup_file_path:
                try:
                    _logger.info(f"Tentative d'exportation de {backup_filename} pour la configuration {self.name}.")
                    self._export_backup_to_remote(backup_file_path, backup_filename, history)
                except Exception as e_export:
                    history.write({'export_status': 'failed', 'export_message': str(e_export)})
                    export_message_suffix = _("\nAVERTISSEMENT: L'exportation distante a échoué: %s") % str(e_export)

            final_message = _('Sauvegarde complète %s créée localement avec succès.') % backup_filename

            if self.export_enabled and history.export_status == 'success':
                final_message += _(' Exportée avec succès.')
            elif export_message_suffix:
                final_message += export_message_suffix

            return {
                'type': 'ir.actions.client', 'tag': 'display_notification',
                'params': {
                    'title': _('Sauvegarde Terminée'), 'message': final_message,
                    'sticky': bool(export_message_suffix),
                    'type': 'success' if not export_message_suffix else 'warning',
                }
            }


        except Exception as e:
            _logger.error(f"Erreur lors de la sauvegarde complète Odoo pour {self.name}: {e}", exc_info=True)
            if os.path.exists(backup_file_path):
                try:
                    os.remove(backup_file_path)
                except Exception as e_rm:
                    _logger.error(
                        f"Impossible de supprimer le fichier de sauvegarde partiel {backup_file_path}: {e_rm}")
            history.write({
                'state': 'failed',
                'message': f"Erreur sauvegarde complète locale: {str(e)}",
                'export_status': 'not_attempted' if self.export_enabled else 'not_applicable',
            })

            raise UserError(_(f"Erreur lors de la sauvegarde complète Odoo pour {self.name}: {e}"))

    def _clean_old_backups(self):
        """Supprime les anciennes sauvegardes selon les règles de rétention."""
        self.ensure_one()
        _logger.info(f"Nettoyage des anciennes sauvegardes pour la configuration: {self.name}")

        # 1. Conservation par nombre de sauvegardes (max_backup_count)
        # Récupérer toutes les sauvegardes réussies pour cette configuration, les plus récentes d'abord
        all_successful_backups = self.env['server.backup.history'].search([
            ('config_id', '=', self.id),
            ('state', '=', 'done')  # On ne nettoie que les sauvegardes 'done'
        ], order='create_date desc')

        if self.max_backup_count > 0 and len(all_successful_backups) > self.max_backup_count:
            # Les sauvegardes à supprimer sont celles qui dépassent le max_backup_count
            # all_successful_backups est trié de la plus récente à la plus ancienne
            # donc on prend à partir de l'index max_backup_count
            backups_to_delete_by_count = all_successful_backups[self.max_backup_count:]
            _logger.info(
                f"Rétention par nombre: {len(all_successful_backups)} sauvegardes trouvées, conservation de {self.max_backup_count}. Suppression de {len(backups_to_delete_by_count)} sauvegardes.")

            for backup in backups_to_delete_by_count:
                try:
                    if backup.file_path and os.path.exists(backup.file_path):
                        os.remove(backup.file_path)
                        _logger.info(f"Fichier supprimé (par nombre): {backup.file_path}")
                    else:
                        _logger.warning(
                            f"Fichier non trouvé ou chemin non défini pour suppression (par nombre): {backup.file_path} pour l'historique ID {backup.id}")

                    backup.write({
                        'state': 'deleted',
                        'message': (
                                               backup.message or "") + f"\nSupprimé par rotation (nombre maximum: {self.max_backup_count})."
                    })
                except Exception as e:
                    _logger.error(
                        f"Erreur lors de la suppression de la sauvegarde {backup.name} (ID: {backup.id}, Chemin: {backup.file_path}) par nombre: {e}")
                    # On pourrait mettre à jour le message de l'historique pour indiquer l'échec de la suppression du fichier
                    backup.write({'message': (
                                                         backup.message or "") + f"\nErreur lors de la suppression du fichier physique: {e}"})

        # 2. Conservation par date (days_to_keep)
        # Il est important de ré-évaluer la liste des backups 'done' car certains ont pu être marqués 'deleted'
        # par la règle de nombre ci-dessus. Ou alors, on peut travailler sur la liste filtrée.
        # Pour simplifier et éviter de supprimer deux fois ou de manquer une suppression,
        # on refait une recherche des backups qui sont *encore* à l'état 'done'.
        current_done_backups_for_date_check = self.env['server.backup.history'].search([
            ('config_id', '=', self.id),
            ('state', '=', 'done'),  # Seulement celles qui sont toujours 'done'
        ], order='create_date asc')  # Trier par date de création la plus ancienne d'abord pour la vérification par date

        if self.days_to_keep > 0:
            cutoff_date = datetime.datetime.now() - datetime.timedelta(days=self.days_to_keep)
            _logger.info(
                f"Rétention par date: conservation des sauvegardes pour {self.days_to_keep} jours. Date limite: {cutoff_date.strftime('%Y-%m-%d %H:%M:%S')}")

            backups_to_delete_by_date = []
            for backup in current_done_backups_for_date_check:  # Parcourt des plus anciennes aux plus récentes
                if backup.create_date < cutoff_date:
                    backups_to_delete_by_date.append(backup)
                else:
                    # Puisque la liste est triée par date de création, on peut arrêter dès qu'on trouve une sauvegarde
                    # qui n'est pas assez vieille pour être supprimée.
                    break

            if backups_to_delete_by_date:
                _logger.info(
                    f"Rétention par date: {len(backups_to_delete_by_date)} sauvegardes à supprimer car antérieures à {cutoff_date.strftime('%Y-%m-%d %H:%M:%S')}.")
                for backup in backups_to_delete_by_date:
                    try:
                        if backup.file_path and os.path.exists(backup.file_path):
                            os.remove(backup.file_path)
                            _logger.info(f"Fichier supprimé (par date): {backup.file_path}")
                        else:
                            _logger.warning(
                                f"Fichier non trouvé ou chemin non défini pour suppression (par date): {backup.file_path} pour l'historique ID {backup.id}")

                        backup.write({
                            'state': 'deleted',
                            'message': (
                                                   backup.message or "") + f"\nSupprimé par rotation (délai de {self.days_to_keep} jours expiré)."
                        })
                    except Exception as e:
                        _logger.error(
                            f"Erreur lors de la suppression de la sauvegarde {backup.name} (ID: {backup.id}, Chemin: {backup.file_path}) par date: {e}")
                        backup.write({'message': (
                                                             backup.message or "") + f"\nErreur lors de la suppression du fichier physique: {e}"})

        _logger.info(f"Nettoyage des anciennes sauvegardes terminé pour la configuration: {self.name}")

    @api.model
    def _process_auto_backups(self):
        """
        Cette méthode est appelée par le cron job.
        Elle parcourt toutes les configurations de sauvegarde actives
        et lance une sauvegarde si nécessaire.
        """
        _logger.info("CRON: Vérification des sauvegardes automatiques à exécuter...")
        active_configs = self.search([
            ('active', '=', True),
            ('auto_backup', '=', True)
        ])

        now = fields.Datetime.now()  # Utiliser fields.Datetime pour être cohérent avec Odoo

        for config in active_configs:
            # Vérifier si next_backup est défini et est dans le passé ou maintenant
            if config.next_backup and config.next_backup <= now:
                _logger.info(
                    f"CRON: Lancement de la sauvegarde automatique pour la configuration : {config.name} (ID: {config.id})")
                try:
                    # Appeler la méthode de sauvegarde pour cette configuration spécifique
                    config._backup_database()
                    _logger.info(f"CRON: Sauvegarde automatique pour {config.name} terminée avec succès.")
                except Exception as e:
                    _logger.error(f"CRON: Erreur lors de la sauvegarde automatique pour {config.name}: {e}")
                    # La méthode _backup_database devrait déjà gérer la création d'un enregistrement d'historique 'failed'.
            # else:
            #     _logger.debug(f"CRON: Pas de sauvegarde nécessaire pour {config.name} (Prochaine: {config.next_backup})")

        _logger.info("CRON: Vérification des sauvegardes automatiques terminée.")
        return True

    def _get_sftp_client(self):
        """Prépare et retourne un client SFTP. Lève une exception en cas d'erreur de connexion."""
        self.ensure_one()
        if not self.sftp_host or not self.sftp_user:
            raise UserError(_("L'hôte SFTP et l'utilisateur SFTP sont requis pour la connexion."))

        try:
            import paramiko  # Tentative d'importation ici pour une meilleure gestion des dépendances
        except ImportError:
            _logger.error("La librairie 'paramiko' est requise pour les transferts SFTP mais n'est pas installée.")
            raise UserError(
                _("La librairie 'paramiko' est requise pour les transferts SFTP. Veuillez l'installer (pip install paramiko)."))

        transport = None
        try:
            transport = paramiko.Transport((self.sftp_host, self.sftp_port or 22))

            private_key_obj = None
            if self.sftp_private_key:
                try:
                    from io import StringIO
                    key_file_obj = StringIO(self.sftp_private_key)
                    # Essayer les types de clés courants
                    try:
                        private_key_obj = paramiko.RSAKey.from_private_key(key_file_obj)
                        key_file_obj.seek(0)  # Réinitialiser pour la prochaine tentative
                    except paramiko.SSHException:
                        try:
                            private_key_obj = paramiko.Ed25519Key.from_private_key(key_file_obj)
                            key_file_obj.seek(0)
                        except paramiko.SSHException:
                            try:
                                private_key_obj = paramiko.DSSKey.from_private_key(key_file_obj)
                                key_file_obj.seek(0)
                            except paramiko.SSHException:
                                try:
                                    private_key_obj = paramiko.ECDSAKey.from_private_key(key_file_obj)
                                except paramiko.SSHException:
                                    _logger.error(
                                        "Format de clé privée SSH non reconnu ou clé protégée par mot de passe non supporté directement ici.")
                                    raise UserError(
                                        _("Format de clé privée SSH non reconnu ou clé protégée par mot de passe. Assurez-vous que la clé n'est pas chiffrée ou utilisez un agent SSH."))
                except Exception as e:
                    _logger.error(f"Erreur lors du chargement de la clé privée SSH : {e}")
                    raise UserError(_(f"Erreur lors du chargement de la clé privée SSH : {e}"))

            if private_key_obj:
                _logger.info(
                    f"Tentative de connexion SFTP à {self.sftp_host}:{self.sftp_port} avec utilisateur {self.sftp_user} et clé SSH.")
                transport.connect(username=self.sftp_user, pkey=private_key_obj)
            elif self.sftp_password:
                _logger.info(
                    f"Tentative de connexion SFTP à {self.sftp_host}:{self.sftp_port} avec utilisateur {self.sftp_user} et mot de passe.")
                transport.connect(username=self.sftp_user, password=self.sftp_password)
            else:
                raise UserError(_("Un mot de passe SFTP ou une clé privée SSH doit être fourni."))

            sftp = paramiko.SFTPClient.from_transport(transport)
            return sftp, transport  # Retourner aussi le transport pour le fermer proprement

        except paramiko.AuthenticationException as e:
            _logger.error(f"Erreur d'authentification SFTP pour {self.sftp_user}@{self.sftp_host}: {e}")
            raise UserError(_(f"Échec de l'authentification SFTP: {e}"))
        except paramiko.SSHException as e:
            _logger.error(f"Erreur SSH lors de la connexion SFTP à {self.sftp_host}: {e}")
            raise UserError(_(f"Erreur de connexion SFTP (SSHException): {e}"))
        except socket.error as e:  # Nécessite import socket
            _logger.error(f"Erreur de socket lors de la connexion SFTP à {self.sftp_host}: {e}")
            raise UserError(_(f"Erreur de connexion SFTP (Socket Error): {e}. Vérifiez l'hôte et le port."))
        except Exception as e:
            _logger.error(f"Erreur inattendue lors de la connexion SFTP à {self.sftp_host}: {e}")
            if transport and transport.is_active():
                transport.close()
            raise UserError(_(f"Erreur inattendue lors de la connexion SFTP: {e}"))

    def action_test_sftp_connection(self):
        self.ensure_one()
        sftp_client = None
        transport = None
        status = 'failed'
        message = ''

        if not self.export_enabled or self.export_type != 'sftp':
            self.write({
                'sftp_connection_status': 'not_tested',
                'sftp_last_test_message': _("L'export SFTP n'est pas activé pour cette configuration.")
            })
            return True

        try:
            sftp_client, transport = self._get_sftp_client()
            # Test simple: lister le contenu du répertoire distant (ou juste vérifier la connexion)
            # Pour un test plus robuste, on peut essayer de lister le répertoire spécifié
            if self.sftp_remote_dir:
                try:
                    sftp_client.listdir(self.sftp_remote_dir)
                    _logger.info(f"SFTP: Accès réussi au répertoire distant {self.sftp_remote_dir}")
                except IOError as e:  # IOError est souvent levée par SFTPClient pour des problèmes de chemin
                    _logger.error(f"SFTP: Impossible d'accéder au répertoire distant {self.sftp_remote_dir}: {e}")
                    raise UserError(
                        _(f"Le répertoire distant SFTP '{self.sftp_remote_dir}' n'est pas accessible ou n'existe pas: {e}"))

            status = 'success'
            message = _("Connexion SFTP réussie à %s.") % self.sftp_host
            _logger.info(message)

        except UserError as e:  # Erreurs déjà formatées pour l'utilisateur
            message = str(e)
            _logger.warning(f"Test de connexion SFTP échoué pour {self.name}: {message}")
        except Exception as e:
            message = _("Échec du test de connexion SFTP: %s") % str(e)
            _logger.error(f"Test de connexion SFTP échoué pour {self.name} avec une erreur inattendue: {e}",
                          exc_info=True)
        finally:
            if sftp_client:
                sftp_client.close()
            if transport and transport.is_active():
                transport.close()

            self.write({
                'sftp_connection_status': status,
                'sftp_last_test_message': message
            })

        # Afficher une notification
        if status == 'success':
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Test de Connexion SFTP'),
                    'message': message,
                    'type': 'success',
                    'sticky': False,
                }
            }
        else:
            # L'erreur est déjà dans sftp_last_test_message, on peut juste rafraîchir la vue.
            # Ou afficher une notification d'échec également.
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Test de Connexion SFTP'),
                    'message': message,  # ou un message plus générique d'échec
                    'type': 'danger',
                    'sticky': True,  # L'utilisateur voudra peut-être lire l'erreur
                }
            }

    def _get_ftp_client(self):
        """Prépare et retourne un client FTP. Lève une exception en cas d'erreur de connexion."""
        self.ensure_one()
        if not self.ftp_host or not self.ftp_user:  # On suppose que ftp_password peut être vide pour anonyme
            raise UserError(_("L'hôte FTP et l'utilisateur FTP sont requis pour la connexion."))

        ftp = None
        try:
            _logger.info(
                f"Tentative de connexion FTP à {self.ftp_host}:{self.ftp_port or 21} avec utilisateur {self.ftp_user}.")
            ftp = ftplib.FTP_TLS(timeout=10)  # Timeout pour l'objet aussi

            ftp.connect(self.ftp_host, self.ftp_port or 21)  # Le timeout de connect est séparé

            # Authentification AVANT d'établir la connexion sécurisée si le serveur le permet,
            # ou après si le serveur attend AUTH TLS d'abord.
            # La plupart des serveurs qui renvoient "530 Non-anonymous sessions must use encryption"
            # s'attendent à AUTH TLS *avant* le login complet pour les sessions non anonymes.
            # Si l'utilisateur est 'anonymous', TLS n'est peut-être pas requis.

            is_anonymous = (self.ftp_user.lower() == 'anonymous')

            if not is_anonymous or self.ftp_require_tls:
                # Tenter d'établir une connexion sécurisée pour les utilisateurs non anonymes
                # ou si l'utilisateur a explicitement demandé TLS.
                _logger.info("FTP: Tentative d'établissement d'une connexion de contrôle sécurisée (AUTH TLS).")
                ftp.auth()  # Négocie TLS/SSL avec le serveur
                _logger.info("FTP: Connexion de contrôle sécurisée établie.")

                # Après AUTH TLS, la protection du canal de données doit être activée
                ftp.prot_p()  # Protection du canal de données (P pour Privé)
                _logger.info("FTP: Protection du canal de données (PROT P) activée.")

            # Maintenant, essayez de vous logger
            ftp.login(self.ftp_user, self.ftp_password or '')
            _logger.info(f"FTP: Login réussi pour l'utilisateur {self.ftp_user}.")

            if self.ftp_use_passive_mode:
                ftp.set_pasv(True)
                _logger.info("FTP: Mode passif activé.")
            else:
                ftp.set_pasv(False)
                _logger.info("FTP: Mode actif activé.")

            return ftp

        except ftplib.error_perm as e:  # Erreurs de permission comme 5xx
            _logger.error(f"Erreur de permission FTP ({e.args[0]}) lors de la connexion à {self.ftp_host}")
            # e.args[0] contient souvent le message d'erreur complet du serveur, ex: "530 Login incorrect."
            if ftp:
                try:
                    ftp.quit()
                except ftplib.all_errors:
                    pass
            # Renvoyer le message d'erreur du serveur directement à l'utilisateur
            raise UserError(_(f"Échec de la connexion FTP: {e.args[0]}"))
        except ftplib.all_errors as e:  # Autres erreurs ftplib
            _logger.error(f"Erreur FTP générique lors de la connexion à {self.ftp_host}: {e}")
            if ftp:
                try:
                    ftp.quit()
                except ftplib.all_errors:
                    pass
            raise UserError(_(f"Échec de la connexion FTP: {e}"))
        except socket.gaierror as e:
            _logger.error(f"Erreur de résolution DNS pour l'hôte FTP {self.ftp_host}: {e}")
            raise UserError(_(f"Impossible de résoudre l'hôte FTP '{self.ftp_host}': {e}"))
        except socket.timeout:
            _logger.error(f"Timeout lors de la connexion FTP à {self.ftp_host}:{self.ftp_port or 21}")
            if ftp:
                try:
                    ftp.quit()
                except ftplib.all_errors:
                    pass
            raise UserError(
                _(f"Timeout lors de la connexion à {self.ftp_host}. Vérifiez l'hôte, le port et la connectivité réseau."))
        except Exception as e:  # Inclut les erreurs SSL si la négociation TLS échoue
            _logger.error(f"Erreur inattendue/SSL lors de la connexion FTPS/FTPES à {self.ftp_host}: {e}")
            if ftp:
                try:
                    ftp.quit()
                except ftplib.all_errors:
                    pass
            raise UserError(_(f"Erreur inattendue ou SSL lors de la connexion FTPS/FTPES: {e}"))

    def action_test_ftp_connection(self):
        self.ensure_one()
        ftp_client = None
        status = 'failed'
        message = ''

        if not self.export_enabled or self.export_type != 'ftp':
            self.write({
                'ftp_connection_status': 'not_tested',
                'ftp_last_test_message': _("L'export FTP n'est pas activé ou sélectionné pour cette configuration.")
            })
            return True  # Pas besoin de notification si l'utilisateur n'a pas demandé FTP

        try:
            ftp_client = self._get_ftp_client()
            # Test simple: lister le contenu du répertoire courant ou du répertoire distant
            # La connexion réussie et le login sont déjà un bon test.
            # Pour un test plus robuste, on peut essayer de changer vers le répertoire distant.
            if self.ftp_remote_dir:
                try:
                    ftp_client.cwd(self.ftp_remote_dir)
                    _logger.info(f"FTP: Accès réussi au répertoire distant {self.ftp_remote_dir}")
                    # Optionnel: lister le contenu pour s'assurer des permissions
                    # ftp_client.retrlines('LIST')
                except ftplib.all_errors as e:
                    _logger.error(f"FTP: Impossible d'accéder au répertoire distant {self.ftp_remote_dir}: {e}")
                    # Certaines erreurs ftplib (comme 550 File unavailable) peuvent être utiles à afficher
                    raise UserError(
                        _(f"Le répertoire distant FTP '{self.ftp_remote_dir}' n'est pas accessible ou n'existe pas: {e}"))

            status = 'success'
            message = _("Connexion FTP réussie à %s.") % self.ftp_host
            _logger.info(message)

        except UserError as e:  # Erreurs déjà formatées pour l'utilisateur
            message = str(e)
            _logger.warning(f"Test de connexion FTP échoué pour {self.name}: {message}")
        except Exception as e:
            message = _("Échec du test de connexion FTP: %s") % str(e)
            _logger.error(f"Test de connexion FTP échoué pour {self.name} avec une erreur inattendue: {e}",
                          exc_info=True)
        finally:
            if ftp_client:
                try:
                    ftp_client.quit()
                except ftplib.all_errors:
                    _logger.warning("Erreur mineure lors de la fermeture de la connexion FTP après test.")
                    pass  # On a déjà le statut principal

            self.write({
                'ftp_connection_status': status,
                'ftp_last_test_message': message
            })

        # Afficher une notification (similaire à SFTP)
        if status == 'success':
            return {
                'type': 'ir.actions.client', 'tag': 'display_notification',
                'params': {'title': _('Test de Connexion FTP'), 'message': message, 'type': 'success', 'sticky': False}
            }
        else:
            return {
                'type': 'ir.actions.client', 'tag': 'display_notification',
                'params': {'title': _('Test de Connexion FTP'), 'message': message, 'type': 'danger', 'sticky': True}
            }

    def _export_backup_to_remote(self, local_file_path, remote_filename, history_record):
        """
        Orchestre l'exportation du fichier de sauvegarde vers la destination distante configurée.
        Met à jour l'enregistrement d'historique avec le statut de l'export.
        """
        self.ensure_one()

        history_record.write({
            'export_status': 'in_progress',
            'export_type': self.export_type,
        })

        try:
            if self.export_type == 'sftp':
                self._transfer_sftp(local_file_path, remote_filename, history_record)
            elif self.export_type == 'ftp':
                self._transfer_ftp(local_file_path, remote_filename, history_record)
            else:
                raise UserError(_("Type d'export '%s' non supporté.") % self.export_type)

            # Si on arrive ici, le transfert spécifique a réussi et a mis à jour l'historique.
            # Pas besoin de le faire ici explicitement sauf si les méthodes de transfert ne le font pas.
            # history_record.write({'export_status': 'success', 'export_message': 'Transfert réussi.'})

        except Exception as e:
            _logger.error(f"Erreur détaillée lors de l'export via {self.export_type} pour {remote_filename}: {e}",
                          exc_info=True)
            history_record.write({
                'export_status': 'failed',
                'export_message': str(e)
            })
            raise  # Relancer l'exception pour que _backup_database la capture et l'affiche

    def _transfer_sftp(self, local_file_path, remote_filename, history_record):
        """Transfère le fichier en utilisant SFTP."""
        self.ensure_one()
        sftp = None
        transport = None

        _logger.info(
            f"SFTP: Début du transfert de {local_file_path} vers {self.sftp_host}:{self.sftp_remote_dir}{remote_filename}")
        remote_full_path = os.path.join(self.sftp_remote_dir or '/', remote_filename).replace('\\',
                                                                                              '/')  # Assurer des slashes Unix

        try:
            sftp, transport = self._get_sftp_client()  # Réutilise la méthode de connexion

            # Vérifier si le répertoire distant existe, sinon essayer de le créer
            try:
                sftp.stat(self.sftp_remote_dir)
            except IOError:  # Souvent [Errno 2] No such file or directory
                _logger.info(f"SFTP: Le répertoire distant {self.sftp_remote_dir} n'existe pas, tentative de création.")
                try:
                    sftp.mkdir(self.sftp_remote_dir)  # Tente de créer le répertoire de base
                    # Pour des chemins imbriqués, il faudrait une création récursive
                except Exception as e_mkdir:
                    _logger.error(f"SFTP: Impossible de créer le répertoire distant {self.sftp_remote_dir}: {e_mkdir}")
                    raise UserError(
                        _("Impossible de créer le répertoire SFTP distant %s: %s") % (self.sftp_remote_dir, e_mkdir))

            _logger.info(f"SFTP: Transfert de '{local_file_path}' vers '{remote_full_path}'")
            sftp.put(local_file_path, remote_full_path)

            _logger.info(f"SFTP: Transfert de {remote_filename} réussi.")
            history_record.write({
                'export_status': 'success',
                'export_remote_path': remote_full_path,
                'export_message': _("Export SFTP réussi vers %s") % remote_full_path
            })

        except Exception as e:
            # Les erreurs de _get_sftp_client sont déjà des UserError.
            # Les autres exceptions (put, mkdir) doivent être encapsulées.
            _logger.error(f"SFTP: Échec du transfert: {e}")
            # history_record est mis à jour par _export_backup_to_remote en cas d'exception
            raise UserError(_("Échec du transfert SFTP: %s") % e)  # ou juste raise e
        finally:
            if sftp: sftp.close()
            if transport and transport.is_active(): transport.close()

    def _transfer_ftp(self, local_file_path, remote_filename, history_record):
        """Transfère le fichier en utilisant FTP."""
        self.ensure_one()
        ftp = None

        _logger.info(
            f"FTP: Début du transfert de {local_file_path} vers {self.ftp_host}:{self.ftp_remote_dir}{remote_filename}")
        # Pour FTP, le chemin distant est relatif au répertoire de login, ou absolu si le serveur le permet.
        # os.path.join n'est pas idéal ici car ftp.cwd et ftp.storbinary gèrent les chemins.
        # On va supposer que ftp_remote_dir est le chemin où on veut aller.

        try:
            ftp = self._get_ftp_client()  # Réutilise la méthode de connexion (qui gère FTPS)

            # Naviguer vers le répertoire distant
            if self.ftp_remote_dir and self.ftp_remote_dir != '/':  # Éviter cwd sur '/' si c'est vide ou juste /
                try:
                    ftp.cwd(self.ftp_remote_dir)
                    _logger.info(f"FTP: Changement vers le répertoire distant {self.ftp_remote_dir} réussi.")
                except ftplib.all_errors as e_cwd:
                    # Si le répertoire n'existe pas, essayer de le créer (simple, pas récursif)
                    _logger.warning(
                        f"FTP: Impossible de changer vers {self.ftp_remote_dir} ({e_cwd}), tentative de création.")
                    try:
                        ftp.mkd(self.ftp_remote_dir)
                        ftp.cwd(self.ftp_remote_dir)  # Essayer de rechanger après création
                        _logger.info(f"FTP: Répertoire distant {self.ftp_remote_dir} créé et sélectionné.")
                    except ftplib.all_errors as e_mkd:
                        _logger.error(
                            f"FTP: Impossible de créer ou d'accéder au répertoire distant {self.ftp_remote_dir}: {e_mkd}")
                        raise UserError(_("Impossible de créer ou d'accéder au répertoire FTP distant %s: %s") % (
                        self.ftp_remote_dir, e_mkd))

            # Transférer le fichier
            _logger.info(
                f"FTP: Transfert de '{local_file_path}' vers '{remote_filename}' dans le répertoire courant du FTP.")
            with open(local_file_path, 'rb') as f_local:
                # STOR écrase le fichier s'il existe. APPE pour append.
                ftp.storbinary(f'STOR {remote_filename}', f_local)

            remote_full_path = f"{ftp.pwd()}/{remote_filename}".replace('//',
                                                                        '/')  # Obtenir le chemin actuel + nom de fichier
            _logger.info(f"FTP: Transfert de {remote_filename} réussi vers {remote_full_path}.")
            history_record.write({
                'export_status': 'success',
                'export_remote_path': remote_full_path,
                'export_message': _("Export FTP réussi vers %s") % remote_full_path
            })

        except Exception as e:
            _logger.error(f"FTP: Échec du transfert: {e}")
            raise UserError(_("Échec du transfert FTP: %s") % e)
        finally:
            if ftp:
                try:
                    ftp.quit()
                except ftplib.all_errors:
                    pass

    def _get_dropbox_client(self):
        self.ensure_one()
        if not all([self.dropbox_app_key, self.dropbox_app_secret, self.dropbox_refresh_token]):
            raise UserError(_("Dropbox App Key, App Secret, et Refresh Token sont requis."))

        try:
            # La SDK gère le refresh en interne si on fournit ces 3 paramètres.
            dbx = dropbox.Dropbox(
                app_key=self.dropbox_app_key,
                app_secret=self.dropbox_app_secret,
                oauth2_refresh_token=self.dropbox_refresh_token
            )
            # Faites un premier appel pour vérifier que tout fonctionne (cela déclenchera un refresh si nécessaire)
            dbx.users_get_current_account()
            _logger.info("Dropbox: Client initialisé avec refresh token. La SDK gérera les access tokens.")
            return dbx
        except dropbox.exceptions.AuthError as e:
            _logger.error(
                f"Dropbox: Erreur d'authentification. Vérifiez App Key, App Secret et Refresh Token. Détails: {e}")
            raise UserError(
                _(f"Échec de l'authentification Dropbox: {e}. Assurez-vous que les identifiants et le refresh token sont corrects et que l'application est autorisée."))
        except dropbox.exceptions.DropboxException as e:
            _logger.error(f"Dropbox: Erreur API Dropbox lors de l'initialisation du client : {e}")
            raise UserError(_(f"Erreur de connexion Dropbox: {e}"))
        except Exception as e:
            _logger.error(f"Dropbox: Erreur inattendue lors de l'initialisation du client : {e}", exc_info=True)
            raise UserError(_(f"Erreur inattendue lors de la connexion à Dropbox: {e}"))

    def action_test_dropbox_connection(self):
        self.ensure_one()
        status = 'failed'
        message = ''

        if not self.export_enabled or self.export_type != 'dropbox':
            self.write({
                'dropbox_connection_status': 'not_tested',
                'dropbox_last_test_message': _("L'export Dropbox n'est pas activé ou sélectionné.")
            })
            return True

        dbx = None
        try:
            dbx = self._get_dropbox_client()  # Lève UserError en cas de problème
            # Test simple: vérifier si on peut lister le contenu du dossier racine ou du dossier spécifié
            # (si on a les droits `files.metadata.read`)
            # ou juste se fier au users_get_current_account() dans _get_dropbox_client.
            # Pour un test plus robuste, on pourrait essayer de lister le dossier distant.
            if self.dropbox_remote_folder and self.dropbox_remote_folder != '/':
                try:
                    _logger.info(f"Dropbox Test: Tentative de lister le contenu de {self.dropbox_remote_folder}")
                    # Pour vérifier l'existence du dossier, on peut essayer de lister son contenu.
                    # S'il est vide ou non existant, list_folder peut lever une erreur ou retourner un résultat spécifique.
                    # Note: list_folder('') liste la racine de l'App Folder ou de Full Dropbox.
                    # Pour un chemin spécifique, il ne doit PAS commencer par '/' s'il est dans l'App Folder.
                    # La documentation Dropbox est un peu ambigüe sur les chemins absolus vs relatifs à l'App Folder.
                    # Pour être sûr : si type App Folder, dropbox_remote_folder doit être SANS '/' au début, ex: 'MesSauvegardes'.
                    # Si type Full Dropbox, '/MesSauvegardes' est OK.
                    # Simplifions : on va juste supposer que le token est valide si _get_dropbox_client réussit.
                    # Un test de création de dossier pourrait être trop intrusif.
                    # dbx.files_list_folder(self.dropbox_remote_folder.strip('/')) # strip('/') pour le chemin
                    _logger.info(
                        f"Dropbox Test: Connexion et authentification au compte réussies. La validité du dossier distant '{self.dropbox_remote_folder}' sera testée lors d'un upload réel.")

                except dropbox.exceptions.ApiError as e:
                    if isinstance(e.error,
                                  dropbox.files.ListFolderError) and e.error.is_path() and e.error.get_path().is_not_found():
                        _logger.warning(
                            f"Dropbox Test: Le dossier distant {self.dropbox_remote_folder} n'existe pas (sera créé lors du premier upload).")
                        # Ce n'est pas nécessairement un échec de connexion, le dossier peut être créé.
                    else:
                        _logger.error(
                            f"Dropbox Test: Erreur API lors du test d'accès au dossier {self.dropbox_remote_folder}: {e}")
                        raise UserError(
                            _(f"Erreur API Dropbox lors du test d'accès au dossier '{self.dropbox_remote_folder}': {e}"))

            status = 'success'
            message = _("Connexion à Dropbox et authentification réussies.")
            _logger.info(message)

        except UserError as e:
            message = str(e)
            _logger.warning(f"Test de connexion Dropbox échoué pour {self.name}: {message}")
        except Exception as e:
            message = _("Échec du test de connexion Dropbox (erreur inattendue): %s") % str(e)
            _logger.error(f"Test de connexion Dropbox échoué pour {self.name} avec une erreur inattendue: {e}",
                          exc_info=True)
        finally:
            # Pas de session à fermer explicitement comme avec FTP/SFTP pour la librairie dropbox Python
            # L'objet dbx sera garbage collecté.
            self.write({
                'dropbox_connection_status': status,
                'dropbox_last_test_message': message
            })

        if status == 'success':
            return {'type': 'ir.actions.client', 'tag': 'display_notification',
                    'params': {'title': _('Test de Connexion Dropbox'), 'message': message, 'type': 'success',
                               'sticky': False}}
        else:
            return {'type': 'ir.actions.client', 'tag': 'display_notification',
                    'params': {'title': _('Test de Connexion Dropbox'), 'message': message, 'type': 'danger',
                               'sticky': True}}

    def _export_backup_to_remote(self, local_file_path, remote_filename, history_record):
        self.ensure_one()
        history_record.write({'export_status': 'in_progress', 'export_type': self.export_type})
        try:
            if self.export_type == 'sftp':
                self._transfer_sftp(local_file_path, remote_filename, history_record)
            elif self.export_type == 'ftp':
                self._transfer_ftp(local_file_path, remote_filename, history_record)
            elif self.export_type == 'dropbox':  # NOUVELLE CONDITION
                self._transfer_dropbox(local_file_path, remote_filename, history_record)
            else:
                raise UserError(_("Type d'export '%s' non supporté.") % self.export_type)
        except Exception as e:
            _logger.error(f"Erreur détaillée lors de l'export via {self.export_type} pour {remote_filename}: {e}",
                          exc_info=True)
            history_record.write({'export_status': 'failed', 'export_message': str(e)})
            raise

    def _transfer_dropbox(self, local_file_path, remote_filename, history_record):
        """Transfère le fichier vers Dropbox."""
        self.ensure_one()
        _logger.info(f"Dropbox: Début du transfert de {local_file_path} vers Dropbox.")

        dbx = None
        try:
            dbx = self._get_dropbox_client()  # Réutilise la méthode de connexion et test initial

            # Normaliser le chemin distant pour Dropbox API :
            # - Doit commencer par '/'
            # - Ne doit pas se terminer par '/' pour un fichier
            # - Le dossier doit exister ou être créé implicitement par l'upload si ce n'est pas la racine.
            #   En fait, files_upload gère la création de dossiers parents si nécessaire.
            folder = self.dropbox_remote_folder.strip()
            if not folder.startswith('/'):
                folder = '/' + folder
            if folder.endswith('/') and len(folder) > 1:  # Eviter de stripper le seul '/' pour la racine
                folder = folder[:-1]

            # Si le dossier est juste "/", on met le fichier à la racine.
            # Sinon, on concatène.
            if folder == '/':
                dropbox_path = f'/{remote_filename}'
            else:
                dropbox_path = f'{folder}/{remote_filename}'

            # Enlever les doubles slashs potentiels
            dropbox_path = dropbox_path.replace('//', '/')

            _logger.info(f"Dropbox: Chemin de destination du fichier : {dropbox_path}")

            # Taille du fichier pour l'upload par morceaux si nécessaire (gros fichiers)
            file_size = os.path.getsize(local_file_path)
            CHUNK_SIZE = 4 * 1024 * 1024  # 4MB par morceau (ajustable)

            with open(local_file_path, 'rb') as f:
                if file_size <= CHUNK_SIZE:
                    # Upload simple pour les petits fichiers
                    _logger.info(f"Dropbox: Upload de {remote_filename} en une seule fois.")
                    dbx.files_upload(f.read(), dropbox_path, mode=dropbox.files.WriteMode.overwrite)
                else:
                    # Upload par morceaux pour les gros fichiers
                    _logger.info(f"Dropbox: Upload de {remote_filename} par morceaux (taille: {file_size} octets).")
                    upload_session_start_result = dbx.files_upload_session_start(f.read(CHUNK_SIZE))
                    cursor = dropbox.files.UploadSessionCursor(session_id=upload_session_start_result.session_id,
                                                               offset=f.tell())
                    commit = dropbox.files.CommitInfo(path=dropbox_path, mode=dropbox.files.WriteMode.overwrite)

                    while f.tell() < file_size:
                        if (file_size - f.tell()) <= CHUNK_SIZE:
                            _logger.info(f"Dropbox: Upload du dernier morceau pour {remote_filename}.")
                            dbx.files_upload_session_finish(f.read(CHUNK_SIZE), cursor, commit)
                        else:
                            _logger.info(f"Dropbox: Upload d'un morceau pour {remote_filename} (offset: {f.tell()}).")
                            dbx.files_upload_session_append_v2(f.read(CHUNK_SIZE), cursor)
                            cursor.offset = f.tell()

            _logger.info(f"Dropbox: Transfert de {remote_filename} réussi vers {dropbox_path}.")
            history_record.write({
                'export_status': 'success',
                'export_remote_path': dropbox_path,
                'export_message': _("Export Dropbox réussi vers %s") % dropbox_path
            })

        except dropbox.exceptions.ApiError as e:
            _logger.error(f"Dropbox: Erreur API Dropbox lors du transfert: {e}", exc_info=True)
            # Essayer de donner un message plus spécifique si possible
            error_details = f"Erreur API Dropbox: {e}"
            if e.error:
                error_details = f"Erreur API Dropbox: {e.user_message_text or e.error}"
            raise UserError(_("Échec du transfert Dropbox: %s") % error_details)
        except Exception as e:
            _logger.error(f"Dropbox: Échec du transfert (erreur inattendue): {e}", exc_info=True)
            raise UserError(_("Échec du transfert Dropbox (erreur inattendue): %s") % e)