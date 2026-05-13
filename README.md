# PT Shortcuts

> **Quand le tryhard est la meilleure solution pour réviser des shortcuts.**

*Made by **notimy** & **Claude** with ♥*

Outil de révision gamifié des raccourcis clavier Pro Tools, conçu à l'origine pour les étudiants de l'**école Acoustik à Montpellier** préparant les certifications Avid (101 → 210). Style Cookie Clicker : score, combo, pouvoirs, achievements, leaderboard en ligne.

Windows + macOS · AZERTY et QWERTY supportés automatiquement · 100 % offline-first.

![Menu principal](docs/screenshots/menu.png)
*[Capture à ajouter]*

---

## ✨ Fonctionnalités

- **8 modules de certification** : 101, 110, 130, 201, 210M, 210P, 205D, 210D
- **Mode classique** progressif : score, combo, timer, déblocage de leçons et de difficulté
- **Mode Custom** : révision libre, sans game over, réponses visibles, pouvoirs gratuits
- **Pouvoirs** : Freeze (gèle le timer), Double (×2 points), Skip, Reveal
- **14 achievements** à débloquer
- **Leaderboard en ligne** (top-10 mondial par certification et difficulté) + highscores locaux
- **AZERTY/QWERTY** : le jeu détecte la position physique des touches indépendamment du layout
- **Mode sans pavé numérique** : pour les claviers de portable (filtre les raccourcis impossibles)
- **Stats détaillées** : taux de réussite par raccourci, par leçon, par certification

![Gameplay](docs/screenshots/gameplay.png)
*[Capture à ajouter]*

---

## 📥 Installation

### Windows

1. Télécharger `PTShortcuts.exe` depuis la page [Releases](https://github.com/nqtimy/ptshortcuts/releases).
2. Double-clic pour lancer. Aucune installation requise.

> Windows SmartScreen peut afficher un avertissement au premier lancement (binaire non signé). Cliquer sur **Informations complémentaires** → **Exécuter quand même**.

### macOS

1. Télécharger `PTShortcuts-mac.zip` depuis la page [Releases](https://github.com/nqtimy/ptshortcuts/releases).
2. Dézipper. Glisser `PTShortcuts.app` dans le dossier **Applications**.
3. **Premier lancement** : clic-droit sur l'icône → **Ouvrir** (contourne Gatekeeper sur les binaires non signés Developer ID).
4. **Accorder les permissions** dans *Réglages Système → Confidentialité et sécurité* :
   - ☑ **Accessibilité** → ajouter PTShortcuts
   - ☑ **Surveillance des entrées** → ajouter PTShortcuts

   Sans ces deux permissions, le jeu ne peut pas détecter les touches.

> ⚠️ À chaque mise à jour, la signature du binaire change. macOS peut redemander de retirer puis re-ajouter l'app dans les deux listes ci-dessus. C'est normal tant que le projet n'a pas de signature Developer ID payante.

> **Important** : toujours lancer l'app via **Finder** ou `open /Applications/PTShortcuts.app`, **jamais** en double-cliquant le binaire interne depuis le Terminal — sinon les permissions d'Accessibilité ne s'appliquent pas.

---

## 🎮 Tutoriel complet

### Démarrer une partie

Sur le menu principal :

- **Flèches gauche/droite** ou clic sur les flèches : naviguer entre les certifications
- **Touches 1 / 2 / 3** ou clic sur les pastilles : choisir la difficulté (Facile / Intermédiaire / Difficile)
- **Champ pseudo** (bas-gauche) : ton nom pour le leaderboard. Sauvegardé automatiquement.
- **Bouton JOUER** : c'est parti.

> 💡 La difficulté 3 (Difficile) se débloque automatiquement après avoir cumulé **200 points à vie** sur la certification choisie. Histoire de chauffer un peu avant le tryhard total.

### Le gameplay

- Une commande Pro Tools s'affiche. **Appuie sur le bon raccourci** sur ton clavier physique.
- **Bonne réponse** → points + combo augmente. Le combo multiplie tes gains.
- **Mauvaise réponse** → combo reset à 0. Le raccourci s'affiche pour que tu mémorises.
- **Timer expire** → game over. Le timer diminue à chaque niveau, donc soit rapide.

Le jeu détecte la **position physique** de la touche, pas le caractère affiché. Sur un clavier AZERTY, la touche imprimée « A » est traitée comme la position QWERTY « Q » (comme Pro Tools le fait). Affichage dual côté droit : ce que l'examen Avid demande (référence QWERTY Mac) + ce que tu dois physiquement presser sur ton clavier.

### Les pouvoirs (powers)

Quatre pouvoirs se débloquent à des paliers de score. Une fois débloqués, ils sont utilisables au prix d'une partie de tes points, **uniquement en cliquant sur leur carte** en bas de l'écran (pas de raccourci clavier, pour ne pas interférer avec les frappes Pro Tools que tu es en train de tester).

- ❄️ **Freeze** — gèle le timer quelques secondes
- ✕2 **Double** — multiplie tes gains de points pendant quelques secondes
- ⏭ **Skip** — passe au raccourci suivant sans pénalité
- 👁 **Reveal** — affiche la réponse (sans valider la frappe)

### Débloquer de nouvelles leçons

Au début d'une certification, seule la première leçon est active. Les autres se débloquent contre des points cumulés via la carte **DÉBLOQUER LEÇON** en jeu.

### Achievements

14 succès à débloquer : enchaîner 5/10/25/50 combos, atteindre 1/10/100/500 bonnes réponses, vitesse, déblocages, etc. Notification slide-in en haut à droite quand tu en débloques un.

### Mode Custom

Pour réviser sans pression : appuie sur **C** au menu (ou clique « Mode Custom »).

- Choisis **plusieurs certifications** à mélanger via les cases à cocher
- 4 options indépendantes :
  - **Timer** : on/off
  - **Bonus gratuits** : tous les pouvoirs débloqués et illimités
  - **Afficher les réponses** : le raccourci attendu est visible en permanence + touches surlignées
  - **Ordre aléatoire** : on/off (off = ordre par difficulté croissante)
- Pas de game over, pas de score sauvegardé, pas d'achievements. Pure révision.

### Leaderboard

- Depuis le menu, touche **L** : ouvre l'écran leaderboard.
- Deux colonnes : tes records locaux par certification/difficulté + top-10 mondial via Supabase.
- Bouton **Refresh** pour rafraîchir le classement en ligne.
- Le jeu fonctionne **offline** : les scores soumis hors-ligne sont sauvegardés et envoyés à la prochaine connexion.

### Stats

Depuis le menu, touche **S** : page de référence complète.

- Carrousel entre les certifications (flèches gauche/droite ou clic)
- Liste de tous les raccourcis groupée par leçon
- Tri (par taux de réussite / vues / nom) et barre de recherche
- Sections repliables/dépliables (clic sur le header de la leçon)

### Mode « Sans pavé numérique »

Toggle en bas-gauche du menu. Si activé, le jeu filtre les raccourcis qui nécessitent **obligatoirement** une touche numpad. Pratique sur un MacBook ou un portable sans pavé numérique. Si un raccourci a une alternative non-numpad (champ `alt`), il reste joué via cette variante.

### Raccourcis menu — récap

| Touche | Action |
|---|---|
| ← → | Naviguer entre certifs (menu et stats) |
| 1 / 2 / 3 | Choisir la difficulté |
| C | Activer/désactiver le Mode Custom |
| S | Ouvrir les Stats |
| L | Ouvrir le Leaderboard |

---

## 🔄 Mise à jour

Les **données utilisateur** (scores, achievements, stats, pseudo) sont stockées séparément du binaire :

| Plateforme | Emplacement |
|---|---|
| Windows | `%APPDATA%\PTShortcuts\save.json` |
| macOS | `~/Library/Application Support/PTShortcuts/save.json` |

**Pour mettre à jour** : télécharge la nouvelle version depuis [Releases](https://github.com/nqtimy/ptshortcuts/releases), remplace l'ancien binaire. Tes données sont préservées automatiquement.

---

## 🛠️ Pour les développeurs

<details>
<summary>Cloner, lancer en local, builder soi-même</summary>

### Stack
- Python 3.12+
- pygame-ce, pynput (Windows), pyobjc-framework-Quartz (macOS)
- PyInstaller pour les builds

### Installation locale

```bash
git clone https://github.com/nqtimy/ptshortcuts.git
cd ptshortcuts
python -m pip install -r requirements.txt
python main.py
```

### Tests

```bash
python -m pytest tests/
```

### Builder un binaire local

- **Windows** : `build.bat` → `dist/PTShortcuts.exe`
- **macOS** : `bash build_mac.sh` → `dist/PTShortcuts.app` + `PTShortcuts.app.zip`

Pour activer le leaderboard en ligne sur un build local, créer un fichier `supabase_config.json` à la racine avec :
```json
{ "url": "https://...", "anon_key": "..." }
```
(Ce fichier est ignoré par git via `.gitignore`. Les builds CI/CD utilisent les secrets GitHub `SUPABASE_URL` / `SUPABASE_ANON_KEY`.)

### Structure
Voir [CLAUDE.md](CLAUDE.md) pour la doc d'architecture complète (modules, format JSON des raccourcis, gestion clavier, etc.).

</details>

---

## 📜 Licence

Distribué sous licence **[Creative Commons BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/deed.fr)** — voir [LICENSE](LICENSE).

En résumé : tu peux librement utiliser, partager et modifier ce projet pour un usage **non commercial**, à condition de **créditer** l'auteur et de redistribuer toute version modifiée sous la **même licence**.

---

## ⚖️ Mentions légales

Pro Tools® et Avid® sont des marques déposées d'Avid Technology, Inc.

Ce projet est un outil pédagogique indépendant, **non affilié à Avid Technology**, créé à des fins éducatives pour soutenir les étudiants préparant les certifications officielles Pro Tools. Les noms de commandes et raccourcis listés proviennent de la documentation officielle des certifications Avid Pro Tools et sont utilisés à des fins purement éducatives.

Aucun matériel propriétaire d'Avid n'est redistribué dans ce projet.
