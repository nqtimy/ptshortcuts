# PT Shortcuts — Pro Tools Keyboard Trainer

## Projet
Jeu Python/Pygame (style Cookie Clicker) pour réviser les raccourcis clavier Pro Tools sur Windows.
Organisé par modules de certification (101, 110, 130, 201, 210M, 210P, 205D, 210D).
Clavier AZERTY Windows, raccourcis basés sur le layout QWERTY Mac de Pro Tools.

## Stack
- Python 3.14, pygame-ce (pas pygame classique — incompatible Python 3.14), pynput
- PyInstaller pour build .exe standalone avec manifest admin UAC
- Pas de framework UI externe, tout est rendu via pygame

## Architecture
```
main.py              → Point d'entrée, boucle principale, dispatch écrans
game/
  config.py          → Constantes (couleurs, points, timers, upgrades)
  loader.py          → Chargement JSON + normalisation touches (keys_mac/keys_win → détection)
  state.py           → GameState (score, combo, upgrades, save/load)
  keyboard.py        → Capture clavier pynput + hook Win32 natif (suppression Win key, scan codes QWERTY)
  particles.py       → Système de particules et popups flottants
  renderer.py        → Fonctions de rendu pygame (texte, boutons, barres, keycaps)
  screens.py         → MenuScreen (carrousel certif/difficulté/review) + GameScreen (jeu + game over)
shortcuts/
  *.json             → Raccourcis par certification (101, 110, 130, 201, 210M, 210P, 205D, 210D)
```

## Format JSON des raccourcis
Chaque shortcut dans les fichiers JSON utilise ce format :
```json
{
  "command_name": "Commit Tracks",
  "context": "Open the Commit Tracks dialog box.",
  "keys_mac": ["Option", "Shift", "C"],
  "keys_win": ["Alt", "Shift", "C"],
  "difficulty": 2,
  "input_type": "key_combo",
  "weight": 5
}
```
- **keys_mac** : notation QWERTY Mac (examen Avid) — affichage référence certif, label "Examen (QWERTY Mac)"
- **keys_win** : notation QWERTY positionnelle — ce que Pro Tools attend (position physique sur clavier QWERTY). Le keyboard handler traduit les frappes AZERTY en positions QWERTY via scan codes, donc keys_win utilise la notation QWERTY (ex: `"A"` = position QWERTY-A = touche physique AZERTY "Q")
- **context** : description fonctionnelle de la commande, SANS mentionner les raccourcis (pas de spoiler)
- **input_type** : `key_combo` (clavier), `modifier_click` (modificateurs + clic souris), `single_key` (touche seule), `key_sequence` (séquence multi-étapes)
- **Mapping modificateurs** : Command→Ctrl, Control→Start/Win, Option→Alt, Shift→Shift
- **Touches alternatives dans une même étape** : `Up/Down Arrow` (accepte Up ou Down), `F1-F4` (accepte F1 à F4), `Numpad 0-5` (accepte Num0 à Num5), `Num+/Num-` (accepte l'un ou l'autre), `AnyDigit` (accepte 0-9 du clavier principal ET Num0-Num9)

Le loader normalise automatiquement les noms de touches JSON vers les noms internes du keyboard handler (ex: `Start`→`Win`, `Numpad 7`→`Num7`, `Up Arrow`→`Up`). Chaque shortcut reçoit des champs `_detect_*` calculés au chargement.

## Input type : key_sequence
Pour les raccourcis multi-étapes (ex : Window Config recall, CKF). `keys_win`/`keys_mac` deviennent des tableaux de tableaux :
```json
{
  "command_name": "Recall Window Configuration",
  "keys_win": [["Num."], ["AnyDigit"], ["Num*"]],
  "keys_mac": [["Num."], ["AnyDigit"], ["Num*"]],
  "input_type": "key_sequence",
  "absorb_steps": [1]
}
```
- Chaque sous-tableau = une étape (combo simultané)
- `absorb_steps` : indices des étapes "absorbantes" — acceptent plusieurs frappes sans avancer. L'étape suivante (end marker) est vérifiée en priorité à chaque frappe. Utilisé pour les chiffres 1-99 des Window Configs.
- Le keyboard state est `clear()`é entre chaque étape réussie → pas de modifier bleed (ex: Ctrl+Alt de l'étape 0 n'interfère pas avec l'étape 1)
- **Ne pas modéliser en key_sequence** les raccourcis où toutes les touches sont pressées simultanément (ex: `Shift+Num+` = `key_combo`, PAS `[["Shift"], ["Num+"]]`)

### CKF (Commands Keyboard Focus)
Raccourcis CKF = key_sequence 2 étapes : `[["Ctrl", "Alt", "1"], ["lettre"]]`
- Step 0 = activation du mode CKF sur la fenêtre Edit (1), Clips List (2), Groups List (3)
- Step 1 = la commande CKF (touche seule, sans modificateurs)
- Le contexte doit mentionner explicitement "Keyboard Focus Mode" pour aider l'utilisateur
- Après step 0, le joueur peut relâcher Ctrl+Alt avant de presser step 1 (clear() automatique)

### Détection key_sequence (screens.py)
`GameScreen._seq_step` track l'étape courante, reset à 0 sur `_next_shortcut()` et sur erreur.
Pour les absorb steps : `peek_last_combo()` (non-destructif) + `consume_last_combo()` — vérifie l'end marker en priorité, sinon accepte le digit et reste sur l'étape.

## Splitter `/` dans _normalize_one_key (loader.py)
La fonction `_normalize_one_key` gère les alternatives via `/` :
- `Num+/Num-` → alternatives `["Num+", "Num-"]`
- `Up/Down Arrow` → alternatives `["Up", "Down"]` (pattern regex dédié, prioritaire)
- `Num/` → une seule partie non-vide après split → pas d'alternative, retourne `["Num/"]`
- `/` seul → parties vides filtrées → tombe en single char → `["/"]`
- **Règle** : le splitter ne s'active que si `len(parts_non_vides) >= 2`

## Détection clavier AZERTY → QWERTY
Le keyboard handler utilise les **scan codes** (position physique de la touche) pour mapper vers les caractères QWERTY US, indépendamment du layout actif. Table `_SCAN_TO_QWERTY` dans `keyboard.py`.

Exemples sur clavier AZERTY :
- Touche physique "A" (AZERTY) → scan 0x10 → QWERTY "Q"
- Touche physique "Q" (AZERTY) → scan 0x1E → QWERTY "A"
- Touche physique "Z" (AZERTY) → scan 0x11 → QWERTY "W"
- Touche physique "W" (AZERTY) → scan 0x2C → QWERTY "Z"

Pour les touches OEM (=, -, /, etc.) non couvertes par la table de scan codes, le fallback utilise `MapVirtualKeyW(vk, MAPVK_VK_TO_CHAR)` qui respecte le layout actif.

## Suppression touche Win (Windows key)
Un hook `WH_KEYBOARD_LL` séparé de pynput (`SetWindowsHookExW` via ctypes) intercepte la touche Win **avant l'OS**. Quand la fenêtre du jeu est au premier plan :
- Win key supprimée → pas de menu Démarrer, pas de Win+V/Win+E etc.
- L'état Win est géré manuellement dans `pressed_modifiers`
- Quand la fenêtre perd le focus → comportement Windows normal
- **Exception** : `Win+L` (verrouillage) est intercepté au niveau kernel, impossible à bloquer (aucun raccourci Pro Tools ne l'utilise)

Ne pas modifier sans bien comprendre les types ctypes 64-bit (`WINFUNCTYPE`, `HMODULE`, `HHOOK`, cast `c_void_p`).

## Affichage dual (examen vs clavier)
Les réponses (reveal, review, game over) montrent les deux notations :
- **"Examen (QWERTY Mac)"** : petit, gris discret — la notation à retenir pour la certification Avid
- **"Ton clavier (AZERTY)"** : grand, bleu vif — ce que l'utilisateur presse physiquement

## Menu principal
- **Carrousel certification** : navigation gauche/droite entre les certifs (CERT_ORDER dans screens.py). Animation slide (position/target lerp, ±110px) + mini bar-chart difficulté dans la carte.
- **Pills difficulté** : 3 boutons cliquables (Facile/Interm./Difficile) avec hover fade. Raccourcis clavier 1/2/3 pour changer directement. Remplace l'ancien carrousel.
- **Mode Révision** : toggle (touche R ou clic) — raccourcis toujours visibles, score non sauvegardé, upgrades désactivés, playlist séquentielle avec reshuffle en boucle, timeout = skip (pas game over).
- **Liens rapides** bas-droite : bouton ALP (ouvre alp.avidlearningcentral.com) et bouton "Choose your vibe" (ouvre playlist YouTube) via `webbrowser.open()`.
- **Coming Soon** : certifs `{'210P', '205D', '210D'}` (constante `COMING_SOON` dans screens.py) — bouton JOUER grisé, non jouables.

## Système d'animation du menu (MenuScreen)
Toutes les animations vivent dans `MenuScreen` (screens.py), pas de thread séparé.

### État persistant dans `__init__`
- `_waveform_phases/speeds` : 40 flottants pour le spectrum analyzer
- `_bg_particles` : liste de particules ambiantes `[x, y, vx, vy, alpha_scale, color_idx]`
- `_particle_layer` : surface SRCALPHA réutilisée pour les particules (évite les allocations)
- `_play_gravity` : `[x, y]` offset magnétique du bouton JOUER
- `_review_mode_t` : `0.0→1.0` transition couleur page (bleu→rouge), lerp à 5%/frame (~1s)
- `_cert_slide_pos/target` : système position/target pour le slide certif sans saccade
- `_cert_left/right_hover_t` : hover fade des flèches de navigation
- `_pill_hover_t` : `[0,0,0]` hover fade des 3 pills difficulté
- `_review/play/alp/vibe_hover_t` : hover fades des boutons
- `_cert_left/right_hover_t` : hover fades des flèches certif

### Animations automatiques (chaque frame)
- **Waveform separator** : 40 barres cylindriques bleu→violet (review: rouge→orange), amplitude sin(), envelope sin(t*π)
- **Particules ambiantes** : 42 points max, montent depuis le bas, parallaxe souris (8px/4px)

### Animations interactives (souris)
- **Spotlight** : reflet blanc radial qui suit la souris dans la carte certif
- **Gravité JOUER** : bouton attrait vers la souris dans un rayon de 120px, lerp 18%/frame
- **Parallaxe particules** : offset `(mouse-center)/w * 8` sur les particules de fond

### Système de couleur dynamique (`page_accent`)
Calculé chaque frame dans `draw()` :
```python
page_accent  = _lc(ACCENT_BLUE, ACCENT_RED, rmt)   # titre, carte, flèches, dot
page_accent2 = _lc(ACCENT_PURPLE, ACCENT_ORANGE, rmt)  # fin du gradient waveform
play_color   = _lc(ACCENT_GREEN, page_accent, rmt)  # bouton JOUER
```
`_lc(c1, c2, t)` est un helper module-level dans screens.py.

### Hover fades
Pattern commun : `hover_t += (target - hover_t) * 0.14` chaque frame.
Les couleurs de fond/bordure/texte sont interpolées avec `_lc()` au lieu de branches if/else abruptes.

## Concepts clés
- **Score** : repart à 0 chaque partie. Upgrades achetés et catégories débloquées persistent via save.json.
- **Combo** : streak de réponses correctes, multiplie les points. Reset à 0 sur erreur.
- **Timer** : diminue avec le niveau. Quand il expire → game over (pas juste skip). En review mode → skip.
- **Difficulté 3** : n'apparaît qu'après 200pts (DIFF3_UNLOCK_SCORE dans config.py).
- **Poids (weight)** : contrôle la fréquence d'apparition via random.choices().
- **Freeze timer** : fonctionne en poussant timer_start en avant de dt chaque frame (dans screens.py update).
- **Pavé numérique + modificateurs** : deux comportements Windows à gérer dans `keyboard.py` :
  1. Quand Shift/Ctrl est tenu avec NumLock ON, Windows substitue le VK de navigation (VK_NEXT) au VK numpad (VK_NUMPAD3). Fix : `_win32_filter` lit `data.vkCode` brut via `_VK_TO_NUMPAD` / `_NAV_VK_TO_NUMPAD` (extended=False).
  2. Windows génère un faux **Shift-up** (driver-level, PAS marqué LLKHF_INJECTED) juste avant la touche numpad et un faux **Shift-down** après, retirant Shift du combo. Fix : détection par scan code — vrai Shift a `scan=0x2A` (gauche) ou `0x36` (droit) ; le faux Shift a `scan=0x22A`. `_win32_filter` pose `_current_injected=True` si VK est Shift et scan hors `{0x2A, 0x36}`.
  Ne pas modifier cette logique sans tester : NumLock ON sans modif, NumLock ON + Shift, NumLock ON + Ctrl, NumLock OFF.

## Ajout d'un nouveau module de certification
Déposer un fichier JSON dans `shortcuts/` avec la structure `keys_mac`/`keys_win`/`input_type` (voir 210M.json).
L'ordre d'affichage est défini dans `CERT_ORDER` (screens.py). Les certifs non listées apparaissent après, par ordre alphabétique.

## Build
`build.bat` ou : `python -m PyInstaller --onefile --windowed --name PTShortcuts --manifest ptshortcuts.manifest --add-data "shortcuts;shortcuts" --add-data "assets;assets" --hidden-import pynput.keyboard._win32 --hidden-import pynput.mouse._win32 main.py`

## Conventions
- Pas de caractères Unicode exotiques dans le rendu (les polices système ne les supportent pas toutes). Utiliser des formes pygame (cercles, rectangles) à la place.
- Le français est utilisé pour l'UI du jeu.
- Les commandes pip doivent passer par `python -m pip` (pip n'est pas dans le PATH).
- Les contextes des raccourcis ne doivent PAS contenir les touches/raccourcis (pas de spoiler).
