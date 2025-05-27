import os
from odoo import api, fields, models, _


class BackupHistory(models.Model):
    _name = 'server.backup.history'
    _description = 'Historique des sauvegardes'
    _order = 'create_date desc'

    name = fields.Char(string='Nom', required=True)
    config_id = fields.Many2one('server.backup.config', string='Configuration', required=True, ondelete='cascade')
    db_name = fields.Char(string='Base de données', required=True)

    create_date = fields.Datetime(string='Date de création', readonly=True)
    file_path = fields.Char(string='Chemin du fichier')
    file_size = fields.Integer(string='Taille (octets)')
    file_size_human = fields.Char(string='Taille', compute='_compute_file_size_human')

    state = fields.Selection([
        ('running', 'En cours'),
        ('done', 'Terminé'),
        ('failed', 'Échoué'),
        ('deleted', 'Supprimé'),
    ], string='État', default='running', required=True)

    export_status = fields.Selection([
        ('not_applicable', 'Non Applicable'),  # Export non activé pour cette config
        ('pending', 'En attente d\'export'),  # Sauvegarde locale réussie, en attente d'export
        ('in_progress', 'Export en cours'),
        ('success', 'Exporté avec succès'),
        ('failed', 'Échec de l\'export'),
        ('not_attempted', 'Non tenté (erreur locale)'),  # Sauvegarde locale échouée
    ], string='Statut Export', default='not_applicable', readonly=True, copy=False)
    export_type = fields.Char(string='Type d\'Export Tenté', readonly=True, copy=False)  # sftp, ftp
    export_remote_path = fields.Char(string='Chemin distant', readonly=True, copy=False)
    export_message = fields.Text(string='Message d\'Export', readonly=True, copy=False)

    message = fields.Text(string='Message')

    @api.depends('file_size')
    def _compute_file_size_human(self):
        for record in self:
            if not record.file_size:
                record.file_size_human = '0 B'
                continue

            # Conversion en format lisible
            size = record.file_size
            for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
                if size < 1024.0:
                    record.file_size_human = f"{size:.2f} {unit}"
                    break
                size /= 1024.0

    def action_download_backup(self):
        self.ensure_one()

        if not self.file_path or not os.path.exists(self.file_path):
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Erreur'),
                    'message': _('Le fichier de sauvegarde n\'existe pas ou n\'est pas accessible.'),
                    'sticky': False,
                    'type': 'danger',
                }
            }

        # TODO: Implémenter la logique pour télécharger le fichier
        # Cela nécessitera un contrôleur HTTP

        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/server.backup.history/{self.id}/download_backup',
            'target': 'self',
        }