"""Achievement definitions for PT Shortcuts."""

# id → {name, desc}
# name: displayed in notification banner
# desc: one-line description
ACHIEVEMENTS = {
    # Combo milestones
    'combo_5':     {'name': 'On fire!',       'desc': 'Atteindre un combo x5'},
    'combo_10':    {'name': 'Chaud devant',   'desc': 'Atteindre un combo x10'},
    'combo_25':    {'name': 'Inarretable',    'desc': 'Atteindre un combo x25'},
    'combo_50':    {'name': 'Legendaire',     'desc': 'Atteindre un combo x50'},
    # Correct answer milestones (cumulative across sessions)
    'correct_1':   {'name': 'Premier pas',    'desc': 'Premiere bonne reponse'},
    'correct_10':  {'name': 'En route',       'desc': '10 bonnes reponses (cumul)'},
    'correct_100': {'name': 'Centurion',      'desc': '100 bonnes reponses (cumul)'},
    'correct_500': {'name': 'Virtuose',       'desc': '500 bonnes reponses (cumul)'},
    # Speed
    'speed_2':     {'name': 'Rapide',         'desc': 'Repondre en moins de 2s'},
    'speed_1':     {'name': 'Eclair',         'desc': 'Repondre en moins de 1s'},
    # Actions
    'reveal_1':    {'name': 'Curieux',        'desc': 'Revealer un raccourci pour la 1ere fois'},
    'upgrade_1':   {'name': 'Investisseur',   'desc': 'Acheter un upgrade'},
    'cat_unlock':  {'name': 'Explorateur',    'desc': 'Debloquer une nouvelle categorie'},
    # Streak
    'no_wrong_10': {'name': 'Sans faute',     'desc': '10 bonnes reponses consecutives'},
}
