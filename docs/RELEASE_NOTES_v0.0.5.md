# PT Shortcuts v0.0.5

### ✨ Nouveautés

- **Ondulations en arrière-plan sur réussite** — une onde « goutte d'eau » se propage depuis l'endroit où le raccourci a été validé, couleur et taille dépendent du combo. À partir d'un combo de 25, l'onde couvre tout l'écran.
- **Aperçu temps réel des touches pressées** — les trois `?` au centre de la carte « APPUYEZ SUR » se remplissent en direct avec les touches que tu maintiens (modificateurs ordonnés Ctrl/Shift/Alt/Win, puis le reste).
- **Feedback ancré au clic** — pour les raccourcis `modifier_click` (Cmd/Ctrl+Clic etc.), les popups « +points » / « RATÉ » et les particules apparaissent exactement à l'endroit du clic, plus à une position fixe. Pour les raccourcis clavier, les popups jittent dans la carte de réponse pour que les events consécutifs restent visuellement distincts.

### 🐛 Corrections

- **Ctrl+Alt+Tab ne fait plus changer de fenêtre sur Windows** — le hook bas-niveau supprime maintenant Alt+Tab et Ctrl+Alt+Tab quand le jeu est au premier plan, donc des raccourcis comme `Tab to Transients` (101/130) se valident sans éjecter le joueur.
- **Distinction Entrée clavier vs Enter pavé numérique** sur Windows et Mac. `Create Memory Location` (110), `New Memory Location` (130), `Edit Memory Location` (201) exigent maintenant le **Enter du pavé numérique**, conformément à Pro Tools. Ils sont aussi correctement masqués en mode « Sans pavé numérique ».
- **Les raccourcis Mac avec `Return` matchent enfin** — bug de normalisation : le handler Mac émet `Enter` mais les JSON avaient `Return`. Concerne 5 raccourcis : `Go to Beginning`, `Go to End`, `Select to Beginning`, `Select to End` (101) et `Return to Song Start Marker` (210M).

### 📋 Corrections de raccourcis (210M, 110, 201)

Plusieurs entrées avaient les labels AZERTY du HTML Avid copiés littéralement au lieu de la notation QWERTY positionnelle. Corrigés :

| Certif | Commande | Avant | Maintenant |
|---|---|---|---|
| 210M | New Playlist | `Start + *` | `Start + \` |
| 210M | Duplicate Playlist | `Ctrl + Start + *` | `Ctrl + Start + \` |
| 210M | Consolidate Selection | `Alt + Shift + "` | `Alt + Shift + 3` |
| 210M | Link Timeline and Edit Selection | `Shift + !` | `Shift + /` |
| 210M | Write to All Enabled | `Ctrl + Alt + !` | `Ctrl + Alt + /` |
| 210M | Open Quantize | `Alt + a` | `Alt + 0` |
| 210M | Increase/Decrease Grid Value | `Shift + -/=` | `Start + Alt + Num+/Num-` |
| 110 | Create Memory Location | `Enter` | `Num Enter` |
| 130 | New Memory Location | `Enter` | `Num Enter` |
| 201 | Edit Memory Location | séquence numpad | `Ctrl + Clic` (modifier_click) |

### 🔧 Interne

- Refactor : `game/screens.py` (3700+ lignes) découpé en package `game/screens/` (`_shared.py`, `menu.py`, `game_screen.py`, `stats.py`, `leaderboard.py`).
- Performance : ondulations actives plafonnées à 6 (FIFO), `GetForegroundWindow()` mis en cache par event, suppression des `random.randint` par frame.
- Nouvelles constantes : `MAX_RIPPLES`, `MODIFIER_ORDER`.
- `.gitignore` : exclusion de l'état local Claude Code.
- 70 tests qui passent.
