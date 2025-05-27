# Module de Sauvegarde Serveur Odoo

Ce module Odoo permet de configurer et d'automatiser la sauvegarde de vos bases de données Odoo, de les stocker localement et de les exporter optionnellement vers des serveurs distants (SFTP, FTP, Dropbox).

**Version:** 0.1
**Auteur:** Pixelblank
**Licence:** LGPL-3

## Table des matières

1.  [Fonctionnalités](#fonctionnalités)
2.  [Prérequis](#prérequis)
3.  [Installation](#installation)
4.  [Configuration](#configuration)
    *   [Paramètres Généraux](#paramètres-généraux)
    *   [Planification](#planification)
    *   [Export Distant](#export-distant)
        *   [SFTP](#sftp)
        *   [FTP](#ftp)
        *   [Dropbox](#dropbox)
5.  [Utilisation](#utilisation)
    *   [Sauvegardes automatiques](#sauvegardes-automatiques)
    *   [Sauvegardes manuelles](#sauvegardes-manuelles)
    *   [Historique des sauvegardes](#historique-des-sauvegardes)
    *   [Test des connexions distantes](#test-des-connexions-distantes)
6.  [Notes importantes](#notes-importantes)
7.  [Dépannage](#dépannage)

## Fonctionnalités

*   **Sauvegardes automatiques et manuelles:** Planifiez des sauvegardes régulières ou lancez-les à la demande.
*   **Stockage local:** Les sauvegardes sont d'abord stockées sur le serveur Odoo.
*   **Format de sauvegarde:** Sauvegardes complètes (base de données SQL + filestore) au format ZIP.
*   **Politiques de rétention:** Configurez combien de jours ou combien de sauvegardes conserver pour éviter de saturer l'espace disque.
*   **Planification flexible:** Définissez des intervalles en minutes, heures, jours ou semaines.
*   **Export distant multiple:**
    *   **SFTP:** Exportez vers un serveur SFTP en utilisant un mot de passe ou une clé SSH privée.
    *   **FTP:** Exportez vers un serveur FTP, avec support du mode passif et de FTPS/FTPES (TLS).
    *   **Dropbox:** Exportez vers un dossier Dropbox en utilisant l'API Dropbox (via OAuth2 Refresh Token).
*   **Test de connexion:** Vérifiez la validité de vos configurations de serveurs distants avant la première sauvegarde.
*   **Historique détaillé:** Suivez l'état de chaque sauvegarde (locale et distante), la taille des fichiers, et les messages d'erreur éventuels.
*   **Notifications:** Recevez des notifications Odoo pour les sauvegardes terminées ou échouées.

## Prérequis

1.  **Odoo:** Une instance Odoo fonctionnelle.
2.  **Dépendances Python:**
    *   `paramiko`: Pour les transferts SFTP.
    *   `dropbox`: Pour les transferts Dropbox.
    Installez-les via pip :
    ```bash
    pip install paramiko dropbox
    ```
3.  **Accès système:**
    *   L'utilisateur système sous lequel Odoo s'exécute doit avoir les **permissions d'écriture** dans le répertoire de sauvegarde configuré (par défaut `/var/lib/odoo/backups`).
    *   Les outils `pg_dump` doivent être accessibles par Odoo (généralement inclus avec l'installation de PostgreSQL).
4.  **Serveur distant (si l'export est utilisé):**
    *   Un serveur SFTP, FTP ou un compte Dropbox avec les identifiants nécessaires.

## Installation

1.  Placez le dossier `server_backup` dans votre répertoire d'addons Odoo.
2.  Assurez-vous que les dépendances Python (`paramiko`, `dropbox`) sont installées dans l'environnement Python de votre Odoo.
3.  Redémarrez le service Odoo.
4.  Connectez-vous à Odoo en tant qu'administrateur.
5.  Allez dans le menu `Applications`, mettez à jour la liste des applications (mode développeur).
6.  Recherchez "Server Backup" et cliquez sur "Installer".

## Configuration

Après l'installation, accédez au module via le menu : **Sauvegardes Serveur > Configurations**.
Cliquez sur "Créer" pour ajouter une nouvelle configuration de sauvegarde.

### Paramètres Généraux

*   **Nom:** Un nom descriptif pour cette configuration (ex: "Sauvegarde Quotidienne Production").
*   **Actif:** Cochez pour activer cette configuration de sauvegarde.
*   **Répertoire de sauvegarde:** Chemin absolu sur le serveur Odoo où les sauvegardes seront stockées localement (par défaut: `/var/lib/odoo/backups`). Assurez-vous que l'utilisateur Odoo a les droits d'écriture.
*   **Format de sauvegarde:** Actuellement, seul "ZIP (Complet: SQL + Filestore)" est supporté.
*   **Jours de conservation:** Nombre de jours pendant lesquels conserver les sauvegardes locales. Les sauvegardes plus anciennes seront supprimées.
*   **Nombre maximum:** Nombre maximum de sauvegardes locales à conserver. Si ce nombre est dépassé, les plus anciennes sont supprimées, même si elles sont plus récentes que le nombre de jours de conservation.

### Planification

*   **Sauvegarde automatique:** Cochez pour activer les sauvegardes automatiques selon l'intervalle défini.
*   **Intervalle:** Unité de temps pour la fréquence des sauvegardes (Minutes, Heures, Jours, Semaines).
*   **Fréquence:** Nombre d'unités d'intervalle (ex: si Intervalle = Jours et Fréquence = 1, une sauvegarde sera effectuée tous les jours).
*   **Prochaine sauvegarde:** Calculée automatiquement en fonction de la dernière sauvegarde réussie et de la planification.

### Export Distant

*   **Activer l'export distant:** Cochez si vous souhaitez exporter les sauvegardes vers un serveur distant après leur création locale.
*   **Type d'export:** Choisissez `SFTP`, `FTP` ou `Dropbox`.

#### SFTP

*   **Hôte SFTP:** Adresse du serveur SFTP.
*   **Port SFTP:** Port du serveur SFTP (par défaut 22).
*   **Utilisateur SFTP:** Nom d'utilisateur pour la connexion SFTP.
*   **Mot de passe SFTP:** Mot de passe pour l'utilisateur SFTP (laissez vide si vous utilisez une clé SSH).
*   **Clé privée SSH:** Contenu de votre clé privée SSH (ex: `id_rsa`). Nécessaire si aucun mot de passe n'est fourni. La clé ne doit pas être protégée par une passphrase.
*   **Répertoire distant SFTP:** Chemin sur le serveur SFTP où stocker les sauvegardes (ex: `/backup/odoo/`).
*   **État de la connexion SFTP / Message du dernier test SFTP:** Mis à jour après un test de connexion.

#### FTP

*   **Hôte FTP:** Adresse du serveur FTP.
*   **Port FTP:** Port du serveur FTP (par défaut 21).
*   **Utilisateur FTP:** Nom d'utilisateur pour la connexion FTP.
*   **Mot de passe FTP:** Mot de passe pour l'utilisateur FTP.
*   **Répertoire distant FTP:** Chemin sur le serveur FTP où stocker les sauvegardes (ex: `/backups/`).
*   **Utiliser le mode passif (PASV):** Recommandé pour la plupart des configurations réseau/pare-feu.
*   **Forcer TLS (FTPS/FTPES):** Cochez si votre serveur FTP exige explicitement TLS (FTPS/FTPES). Sinon, le module tentera de négocier TLS si le serveur le propose.
*   **État de la connexion FTP / Message du dernier test FTP:** Mis à jour après un test de connexion.

#### Dropbox

*   **Dropbox App Key:** Votre "App key" obtenue depuis la console développeur Dropbox.
*   **Dropbox App Secret:** Votre "App secret" obtenu depuis la console développeur Dropbox.
*   **Dropbox Refresh Token:** Le "Refresh Token" à longue durée obtenu via le processus OAuth2 initial. Ce token permet au module de générer des "Access Tokens" de courte durée sans intervention manuelle.
    *   **Note pour obtenir le Refresh Token:** Vous devrez généralement créer une application Dropbox (type "Scoped Access", avec permissions `files.content.write` et `files.content.read`, et `account_info.read` pour tester la connexion). Ensuite, utilisez un script ou un outil pour générer un "Authorization Code" puis l'échanger contre un "Refresh Token". Consultez la documentation de l'API Dropbox pour le flux "OAuth 2 authorization code flow with PKCE" (pour les applications sans serveur backend direct pour l'utilisateur) ou "OAuth 2 authorization code flow" (si vous pouvez gérer une redirection).
*   **Dossier distant Dropbox:** Chemin du dossier dans Dropbox où stocker les sauvegardes (ex: `/OdooBackups/`). Doit commencer et se terminer par un `/`. Si vous utilisez un type d'application "App folder", ce chemin est relatif à ce dossier d'application.
*   **État de la connexion Dropbox / Message du dernier test Dropbox:** Mis à jour après un test de connexion.

## Utilisation

### Sauvegardes automatiques

Si la "Sauvegarde automatique" est activée dans une configuration, le planificateur cron d'Odoo (`Sauvegarde: Planificateur de sauvegardes automatiques`) vérifiera toutes les minutes si des sauvegardes sont dues. Si `next_backup` est dans le passé, une sauvegarde sera lancée pour cette configuration.

### Sauvegardes manuelles

Depuis la vue formulaire d'une configuration de sauvegarde, cliquez sur le bouton **"Sauvegarder maintenant"** pour lancer une sauvegarde immédiatement.

### Historique des sauvegardes

Allez dans **Sauvegardes Serveur > Historique** pour voir la liste de toutes les tentatives de sauvegarde. Vous y trouverez :
*   Le nom du fichier de sauvegarde.
*   La date de la sauvegarde.
*   La configuration associée.
*   L'état local (En cours, Terminé, Échoué, Supprimé).
*   La taille du fichier.
*   L'état de l'export distant (si applicable).
*   Les messages d'erreur ou de succès.

### Test des connexions distantes

Depuis la vue formulaire d'une configuration de sauvegarde, si l'export distant est activé, des boutons de test apparaissent :
*   **"Tester Connexion SFTP"**
*   **"Tester Connexion FTP"**
*   **"Tester Connexion Dropbox"**

Utilisez ces boutons pour vérifier que vos paramètres de connexion distante sont corrects. Le résultat du test sera affiché dans les champs "État de la connexion..." et "Message du dernier test...".

## Notes importantes

*   **Permissions des fichiers:** Assurez-vous que l'utilisateur Odoo a les permissions de lecture/écriture sur le `Répertoire de sauvegarde` configuré.
*   **Cron Odoo:** Le job cron "Planificateur de sauvegardes automatiques" est configuré pour s'exécuter toutes les minutes. Il ne lance une sauvegarde que si la date `Prochaine sauvegarde` d'une configuration active est dépassée.
*   **Espace disque:** Surveillez l'espace disque sur votre serveur Odoo (pour les sauvegardes locales) et sur votre serveur distant.
*   **Sécurité:** Protégez bien vos identifiants de connexion distante (mots de passe, clés SSH, tokens Dropbox). Les champs de mot de passe et tokens sont masqués dans l'interface Odoo.
*   **Ressources serveur:** Les sauvegardes, en particulier le dump du filestore, peuvent consommer des ressources CPU et I/O. Planifiez-les pendant les heures de faible activité si possible.
*   **Dropbox App Permissions:** Pour Dropbox, si vous créez une application de type "App folder", les sauvegardes seront stockées dans un dossier dédié à votre application dans Dropbox. Si vous choisissez "Full Dropbox", l'application aura accès à l'ensemble du Dropbox de l'utilisateur (nécessite plus de prudence). Les permissions minimales requises sont `files.content.write` (pour uploader) et `files.content.read` (potentiellement pour des vérifications futures, ou si vous voulez lister des fichiers), et `account_info.read` (pour le test de connexion `users_get_current_account`).

## Dépannage

*   **Échec de la sauvegarde locale:**
    *   Vérifiez les logs Odoo pour des messages d'erreur détaillés.
    *   Assurez-vous que l'utilisateur Odoo a les droits d'écriture sur le `Répertoire de sauvegarde`.
    *   Vérifiez que `pg_dump` est accessible et fonctionne correctement.
    *   Vérifiez l'espace disque disponible.
*   **Échec de l'export distant:**
    *   Utilisez le bouton "Tester Connexion..." pour diagnostiquer les problèmes de connexion.
    *   Vérifiez les logs Odoo.
    *   **SFTP/FTP:** Assurez-vous que les pare-feux (locaux et distants) autorisent la connexion sur le port spécifié. Vérifiez les droits d'écriture dans le répertoire distant.
    *   **Dropbox:** Assurez-vous que votre App Key, App Secret et Refresh Token sont corrects et que le token n'a pas été révoqué. Vérifiez les permissions de votre application Dropbox.
*   **Dépendances Python non trouvées:** Si vous voyez des erreurs comme `ImportError: No module named paramiko` ou `ImportError: No module named dropbox`, assurez-vous d'avoir installé ces librairies dans l'environnement Python utilisé par Odoo.