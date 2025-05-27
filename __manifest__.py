{
    'name': "Server Backup",
    'summary': """
        Module de sauvegarde des bases de données Odoo sur le serveur et export vers serveur distant
    """,
    'description': """
        Ce module permet de :
        - Configurer des sauvegardes automatiques des bases de données
        - Stocker localement les sauvegardes sur le serveur Odoo
        - Exporter les sauvegardes vers un serveur distant
        - Gérer la rotation et la conservation des sauvegardes
    """,
    'author': "Pixelblank",
    'category': 'Administration',
    'version': '1.6',
    'depends': ['base'],
    'external_dependencies': {
        'python': ['paramiko'],
    },
    'data': [
        'security/ir.model.access.csv',
        'views/backup_config_views.xml',
        'views/backup_history_views.xml',
        'data/cron_data.xml',
    ],
    'images': ['static/description/icon.png'],
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}