# PT Shortcuts — Pro Tools Keyboard Trainer

## Projet
Jeu Python/Pygame (style Cookie Clicker) pour réviser les raccourcis clavier Pro Tools.
Cible principale : postes Mac partagés d'une école audio (AZERTY ou QWERTY selon poste).
Organisé par modules de certification (101, 110, 130, 201, 210M, 210P, 205D, 210D).

## Stack
- Python 3.12 (CI/CD) / 3.14 (dev local), pygame-ce (pas pygame classique), pynput
- PyInstaller pour build standalone (.exe Windows / binaire Mac)
- Supabase (REST via urllib, pas de SDK externe) pour le leaderboard en ligne
- Pas de framework UI externe, tout est rendu via pygame

## Architecture
```
main.py              → Point d'entrée, boucle principale, dispatch écrans
game/
  config.py          → Constantes (couleurs, points, timers, upgrades, IS_MAC)
  loader.py          → Chargement JSON + normalisation touches + poids adaptatifs
  state.py           → GameState (score, combo, upgrades, save/load, pseudo, stats)
  keyboard/
    __init__.py      → Dispatch plateforme (win32 → win.py, darwin → mac.py)
    base.py          → BaseKeyboardHandler (ABC) — interface commune
    win.py           → Windows : pynput + hook Win32 (scan codes AZERTY→QWERTY)
    mac.py           → macOS : pynput + CGEventTap Quartz (Cmd suppression)
  achievements.py    → 14 achievements, détection + save/load
  leaderboard.py     → Highscore local + Supabase REST async (offline-first)
  particles.py       → Système de particules et popups flottants
  renderer.py        → Fonctions de rendu pygame (texte, boutons, barres, keycaps)
  screens.py         → MenuScreen, GameScreen, StatsScreen, LeaderboardScreen
shortcuts/
  *.json             → Raccourcis par certification (101, 110, 130, 201, 210M, 210P, 205D, 210D)
supabase_config.json → URL + anon key Supabase (non commité) — embarqué dans l'exe au build
build.bat            → Build PyInstaller Windows (embarque supabase_config.json si présent)
build_mac.sh         → Build PyInstaller macOS (embarque supabase_config.json si présent)
.github/workflows/
  build.yml          → CI/CD : build Windows + Mac → GitHub Release sur tag v*
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
- **Types de clic** (pour `modifier_click`) : `Click` (clic gauche), `Right-Click` (clic droit), `Double-Click` (double-clic gauche, fenêtre 400ms)
- **Touches alternatives dans une même étape** : `Up/Down Arrow` (accepte Up ou Down), `F1-F4` (accepte F1 à F4), `Numpad 0-5` (accepte Num0 à Num5), `Num+/Num-` (accepte l'un ou l'autre), `AnyDigit` (accepte 0-9 du clavier principal ET Num0-Num9)

Le loader normalise automatiquement les noms de touches JSON vers les noms internes du keyboard handler (ex: `Start`→`Win`, `Numpad 7`→`Num7`, `Up Arrow`→`Up`). Chaque shortcut reçoit des champs `_detect_*` calculés au chargement.

## Raccourcis alternatifs (`alt`)
Quand une commande a plusieurs raccourcis valides (ex: Begin Recording = Cmd+Space / F12 / Numpad 3), on utilise le champ `alt` :
```json
{
  "command_name": "Begin Recording",
  "keys_mac": ["Command", "Space"],
  "keys_win": ["Ctrl", "Space"],
  "alt": [
    {"keys_mac": ["F12"], "keys_win": ["F12"], "input_type": "single_key"},
    {"keys_mac": ["Numpad 3"], "keys_win": ["Numpad 3"], "input_type": "single_key"}
  ],
  "input_type": "key_combo",
  ...
}
```
- Chaque entrée `alt` a ses propres `keys_mac`, `keys_win`, et `input_type` (peut différer du principal)
- Le loader construit `_detect_alt` : liste de dicts avec les mêmes champs `_detect_*` que le raccourci principal
- **Détection** : `GameScreen.update()` vérifie le raccourci principal, puis chaque alt via `_check_alt_combo()` avant de déclarer "faux". Pour `modifier_click`, les alts sont aussi vérifiés dans `handle_event()`
- **Affichage** : reveal/game over montrent les alternatives avec "ou" entre chaque ; `StatsScreen._fmt_keys()` les sépare par " / "
- **Stats** : les alternatives partagent le même `command_name`, donc les stats (views, correct) sont comptabilisées ensemble

## Input type : modifier_click (clic souris + modificateurs)
Trois types de clic supportés, distingués par `_detect_click` calculé par `_build_detect_info` dans loader.py :
- `'left'` → JSON `"Click"` (clic gauche simple)
- `'right'` → JSON `"Right-Click"` (clic droit)
- `'double'` → JSON `"Double-Click"` (double-clic gauche)

Exemple (110, Create Audio Track from Empty Space) :
```json
{
  "command_name": "Create Audio Track from Empty Space",
  "keys_mac": ["Command", "Double-Click"],
  "keys_win": ["Ctrl", "Double-Click"],
  "input_type": "modifier_click"
}
```

### State machine du double-clic (GameScreen)
La détection vit dans `handle_event()` (event-driven, pas de polling). Deux champs d'état dans `GameScreen` :
- `self._dblclick_time` : `time.time()` du premier clic (0.0 = pas de clic en attente)
- constante module `_DBLCLICK_THRESHOLD = 0.4` secondes entre les deux clics

Flow du helper `_try_double(mods_expected)` :
1. Modificateurs incorrects → retourne `'wrong'` (réinitialise `_dblclick_time`)
2. Modificateurs corrects ET un premier clic a été enregistré il y a moins de 400ms → `'correct'` (succès)
3. Modificateurs corrects, pas de premier clic récent → `'wait'` (enregistre ce clic, attend le second)

`self._dblclick_time` est reset à 0.0 dans `_next_shortcut()` (les deux chemins : correct/wrong) pour éviter qu'un clic d'un raccourci précédent soit compté sur le suivant.

### Affichage
- **Hint in-game** : "Maintenez les touches + Double-clic" (vs "... + Clic souris") selon `sc.get('_detect_click') == 'double'`
- **Reveal / game over** : label "(Modificateurs + Double-clic)" vs "(Modificateurs + Clic souris)"
- **Stats `_fmt_keys`** : affiche `double-clic` / `clic droit` / `clic` en français

## Reconstruction des JSON de certification
Les fichiers JSON dans `shortcuts/` sont reconstruits certification par certification depuis les HTML officiels Avid (ex: `101_2023_.html`). Processus :
1. Parser le HTML (table 2 colonnes : description + raccourci)
2. Dédupliquer les commandes répétées entre lessons
3. Exclure les opérations de drag pur (non détectables) et actions trop contextuelles. Le double-clic est supporté (`"Double-Click"` dans `keys_mac`/`keys_win`).
4. Identifier les commandes avec plusieurs raccourcis valides → champ `alt`
5. Organiser par lessons thématiques
6. Vérifier que le JSON charge correctement via `load_certifications()`

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
Le keyboard handler utilise les **scan codes** (position physique de la touche) pour mapper vers les caractères QWERTY US, indépendamment du layout actif. Table `_SCAN_TO_QWERTY` dans `keyboard/win.py`.

Exemples sur clavier AZERTY :
- Touche physique "A" (AZERTY) → scan 0x10 → QWERTY "Q"
- Touche physique "Q" (AZERTY) → scan 0x1E → QWERTY "A"
- Touche physique "Z" (AZERTY) → scan 0x11 → QWERTY "W"
- Touche physique "W" (AZERTY) → scan 0x2C → QWERTY "Z"

Pour les touches OEM (=, -, /, etc.) non couvertes par la table de scan codes, le fallback utilise `MapVirtualKeyW(vk, MAPVK_VK_TO_CHAR)` qui respecte le layout actif.

Sur Mac, `keyboard/mac.py` utilise les **VK codes** (kVK_ANSI_*) via `_MAC_VK_TO_QWERTY` pour le même résultat indépendant du layout.

## Suppression touche Win (Windows) / Cmd (Mac)
**Windows** : hook `WH_KEYBOARD_LL` séparé de pynput (`SetWindowsHookExW` via ctypes) intercepte la touche Win avant l'OS. Quand la fenêtre est au premier plan : Win supprimée, état géré dans `pressed_modifiers`. `Win+L` impossible à bloquer (kernel).

**Mac** : `CGEventTap` via `pyobjc-framework-Quartz` supprime les events Cmd. Nécessite permission Accessibilité (Réglages Système → Confidentialité → Accessibilité). Si refusée, fallback silencieux (jeu fonctionnel, Cmd+H/Q restent actifs).

Ne pas modifier la logique Win32 sans bien comprendre les types ctypes 64-bit (`WINFUNCTYPE`, `HMODULE`, `HHOOK`, cast `c_void_p`).

## Affichage dual (examen vs clavier)
Les réponses (reveal, review, game over) montrent les deux notations via des constantes dans screens.py :
```python
if IS_MAC:
    _LABEL_SMALL = "Reference Windows"; _LABEL_BIG = "Ton clavier (Mac)"
    _KEYS_SMALL = 'keys_win'; _KEYS_BIG = 'keys_mac'; _COLOR_BIG = ACCENT_GREEN
else:
    _LABEL_SMALL = "Examen (QWERTY Mac)"; _LABEL_BIG = "Ton clavier (AZERTY)"
    _KEYS_SMALL = 'keys_mac'; _KEYS_BIG = 'keys_win'; _COLOR_BIG = ACCENT_BLUE
```
- **petit/gris** : notation de référence (ce que l'examen Avid demande)
- **grand/coloré** : ce que l'utilisateur presse physiquement sur son clavier

## Menu principal
- **Carrousel certification** : navigation gauche/droite entre les certifs (CERT_ORDER dans screens.py). Animation slide (position/target lerp, ±110px) + mini bar-chart difficulté dans la carte.
- **Pills difficulté** : 3 boutons cliquables (Facile/Interm./Difficile) avec hover fade. Raccourcis clavier 1/2/3 pour changer directement.
- **Mode Révision** : toggle (touche R ou clic) — raccourcis toujours visibles, score non sauvegardé, upgrades désactivés, playlist séquentielle avec reshuffle en boucle, timeout = skip (pas game over).
- **Pseudo** : champ saisie bas-gauche, persisté dans save.json, utilisé pour le leaderboard.
- **Liens rapides** bas-droite : bouton ALP et bouton "Choose your vibe" via `webbrowser.open()`.
- **Coming Soon** : certifs `{'210P', '205D', '210D'}` (constante `COMING_SOON` dans screens.py) — bouton JOUER grisé.
- **Touches** : S → StatsScreen, L → LeaderboardScreen, R → toggle review mode.

## Système d'animation du menu (MenuScreen)
Toutes les animations vivent dans `MenuScreen` (screens.py), pas de thread séparé.

### État persistant dans `__init__`
- `_waveform_phases/speeds` : 40 flottants pour le spectrum analyzer
- `_bg_particles` : liste de particules ambiantes `[x, y, vx, vy, alpha_scale, color_idx]`
- `_particle_layer` : surface SRCALPHA réutilisée pour les particules (évite les allocations)
- `_play_gravity` : `[x, y]` offset magnétique du bouton JOUER
- `_review_mode_t` : `0.0→1.0` transition couleur page (bleu→rouge), lerp à 5%/frame (~1s)
- `_cert_slide_pos/target` : système position/target pour le slide certif sans saccade
- `_pill_hover_t` : `[0,0,0]` hover fade des 3 pills difficulté
- Divers `_*_hover_t` : hover fades des boutons et flèches

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
`_lc(c1, c2, t)` et `_lf(k, dt)` sont des helpers module-level dans screens.py.
`_lf(k, dt) = 1.0 - (1.0 - k) ** (dt * 60.0)` — lerp frame-rate independent.

### Hover fades
Pattern commun : `hover_t += (target - hover_t) * _lf(0.14, dt)` chaque frame.
Les couleurs de fond/bordure/texte sont interpolées avec `_lc()`.

## Concepts clés
- **Score** : repart à 0 chaque partie. Upgrades achetés et catégories débloquées persistent via save.json.
- **Combo** : streak de réponses correctes, multiplie les points. Reset à 0 sur erreur.
- **Timer** : diminue avec le niveau. Quand il expire → game over (pas juste skip). En review mode → skip.
- **Difficulté 3** : n'apparaît qu'après 200pts (DIFF3_UNLOCK_SCORE dans config.py).
- **Poids adaptatifs** : `get_weighted_shortcuts()` dans loader.py ajuste le weight selon le taux de réussite. `factor = max(0.3, 2.0 - 1.7 * rate)` — les raccourcis ratés apparaissent plus souvent.
- **Freeze timer** : fonctionne en poussant timer_start en avant de dt chaque frame (dans screens.py update).
- **Pavé numérique + modificateurs** : deux comportements Windows à gérer dans `keyboard/win.py` :
  1. Quand Shift/Ctrl est tenu avec NumLock ON, Windows substitue le VK de navigation au VK numpad. Fix : `_win32_filter` lit `data.vkCode` brut via `_VK_TO_NUMPAD` / `_NAV_VK_TO_NUMPAD` (extended=False).
  2. Windows génère un faux Shift-up/down driver-level avant/après chaque touche numpad. Fix : détection par scan code — vrai Shift a `scan=0x2A` (gauche) ou `0x36` (droit) ; le faux a `scan=0x22A`.
  Ne pas modifier cette logique sans tester : NumLock ON sans modif, NumLock ON + Shift, NumLock ON + Ctrl, NumLock OFF.

## Achievements (game/achievements.py)
14 achievements : `combo_5/10/25/50`, `correct_1/10/100/500`, `speed_2/speed_1`, `reveal_1`, `upgrade_1`, `cat_unlock`, `no_wrong_10`.
Notification slide-in/out en haut à droite dans GameScreen (`_draw_achievements()`), durée 3.3s.
Persistés dans save.json (merge des IDs existants pour préserver les timestamps).

## Leaderboard (game/leaderboard.py)
- `supabase_config.json` (non commité) : `{"url": "...", "anon_key": "..."}` — clé anon Supabase.
- Résolution du fichier (`_config_path()`) : en mode bundled, cherche d'abord dans `sys._MEIPASS` (embarqué dans l'exe), puis à côté de l'exe (override utilisateur). En dev, cherche à la racine du projet.
- `save_local_highscore()` : compare avec `highscores` dans save.json, retourne True si nouveau record.
- `submit_score_async()` : file d'attente `_pending_scores`, sync en thread background sur chaque `_save()`.
- `fetch_online_scores_async()` : fetch Supabase REST en background, callback sur résultat.
- Offline-first : les scores en attente sont persistés dans save.json et envoyés à la prochaine connexion.
- Supabase REST via `urllib.request` (stdlib uniquement, aucune dépendance externe).
- `LeaderboardScreen` : deux colonnes (highscores locaux par difficulté + top-10 global), bouton refresh.

## Stats (screens.py → StatsScreen)
Écran de référence complet, accessible depuis le menu (touche S).

### Fonctionnalités
- **Carrousel certif** : navigation gauche/droite (flèches clavier ou clic souris) entre toutes les certifications chargées. Animation slide + dots de position. Instancié avec `StatsScreen(certifications, initial_cert)` (reçoit le dict complet).
- **Liste scrollable** : tous les raccourcis de la certif sélectionnée, triables par taux de réussite / vues / nom alphabétique.
- **Barre de recherche** : champ texte à droite des boutons de tri. Filtre en temps réel sur `command_name`, `context`, `category`, `keys_win`, `keys_mac`. Quand active, les flèches gauche/droite ne naviguent plus entre certifs. Echap efface la requête, second Echap déselectionne le champ. Le résumé affiche `N/total raccourcis` quand un filtre est actif.
- **Par ligne** (hauteur 62px) : nom de la commande, contexte tronqué à la largeur de colonne, catégorie, raccourcis Win (ACCENT_BLUE) · Mac (TEXT_DIM ou ACCENT_GREEN sur Mac).

### Architecture interne
- `_rows` : liste triée complète ; `_display_rows` : liste filtrée par la recherche. `_clamp_scroll` et le rendu utilisent `_display_rows`.
- `_apply_filter()` recalcule `_display_rows` depuis `_rows` + `_search_query`. Appelé par `_build_rows()` et à chaque frappe.
- `_fmt_keys(sc, field)` : formate les touches en texte compact (`Ctrl+Alt+C`, steps séparés par `>`).
- **Piège** : certains champs JSON (`context`, `category`) peuvent être `null` → utiliser `sc.get('field') or ''` et non `sc.get('field', '')` (le défaut `''` n'est pas utilisé si la valeur est explicitement `None`).

## Clavier visuel (screens.py → GameScreen._draw_keyboard)
Layout QWERTY Mac en 5 rangées (`_KB_ROWS`), unités de largeur proportionnelles.
`highlight_keys` (bleu) = touches pressées, `expected_keys` (vert/violet) = réponse attendue en review.
`_get_expected_keys()` retourne les touches de l'étape courante pour key_sequence.

## Ajout d'un nouveau module de certification
Déposer un fichier JSON dans `shortcuts/` avec la structure `keys_mac`/`keys_win`/`input_type` (voir 210M.json).
L'ordre d'affichage est défini dans `CERT_ORDER` (screens.py). Les certifs non listées apparaissent après, par ordre alphabétique.

## Build
**Windows** : `build.bat` (recommandé) — installe les dépendances, embarque `supabase_config.json` si présent, génère `dist/PTShortcuts.exe`.

Commande manuelle :
```
python -m PyInstaller --onefile --windowed --name PTShortcuts --manifest ptshortcuts.manifest --add-data "shortcuts;shortcuts" --add-data "supabase_config.json;." --hidden-import pynput.keyboard._win32 --hidden-import pynput.mouse._win32 main.py
```

**macOS** : `bash build_mac.sh` — embarque `supabase_config.json` si présent. PyInstaller, pyobjc-framework-Quartz optionnel pour suppression Cmd.

**CI/CD** : `.github/workflows/build.yml` — déclenché sur push `main` ou tag `v*`. Crée une GitHub Release avec les deux binaires sur tag.
Pour embarquer Supabase dans les releases CI, ajouter deux secrets GitHub (`Settings → Secrets → Actions`) :
- `SUPABASE_URL` — URL du projet Supabase
- `SUPABASE_ANON_KEY` — clé anon (safe à exposer côté client, sécurité assurée par les policies RLS)

## Tests
`tests/test_loader.py` (36 tests) + `tests/test_keyboard.py` (34 tests) = 70 tests. Lancer : `python -m pytest tests/`.
Couvre normalisation des touches, validation, détection (clicks `left`/`right`/`double`), et handlers plateforme.

## Conventions
- Pas de caractères Unicode exotiques dans le rendu (les polices système ne les supportent pas toutes). Utiliser des formes pygame (cercles, rectangles) à la place.
- Le français est utilisé pour l'UI du jeu.
- Les commandes pip doivent passer par `python -m pip` (pip n'est pas dans le PATH).
- Les contextes des raccourcis ne doivent PAS contenir les touches/raccourcis (pas de spoiler).
- Saves atomiques : écriture dans fichier tmp + `os.replace()` pour éviter la corruption sur crash.
- `supabase_config.json` ne doit PAS être commité (contient la clé anon). Il est embarqué dans l'exe au build via `--add-data`.
- Chemin de sauvegarde (bundled) : `%APPDATA%\PTShortcuts\save.json` (Windows) / `~/Library/Application Support/PTShortcuts/save.json` (Mac). En dev (`main.py`) : racine du projet.
