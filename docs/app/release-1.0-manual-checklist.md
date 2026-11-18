# Release 1.0.0.0 : vérifications manuelles avant le go

Checklist à faire à la main dans l'app avant de publier la release v1.0.0.0, sur Path of Radiance (POR)
et Radiant Dawn (RD). Les tests automatiques (CI et tests disque) couvrent les formats ; cette liste
couvre ce qu'ils ne voient pas : les écrans, la sauvegarde, le rechargement et le jeu dans Dolphin.

Durée : environ 3 h pour tout, ou 1 h 15 pour le seul bloc **Priorité** (marqué ⭐).
Pour un échec, noter le numéro de la ligne et faire une capture d'écran.

Le cycle de base pour chaque éditeur, noté **M/S/R** :

1. **M**odifier une valeur visible (noter l'ancienne).
2. **S**auvegarder avec le bouton de l'éditeur ; la barre d'état ne liste plus l'éditeur comme non sauvegardé.
3. **R**echarger : fermer le projet (**File ▸ Close Project**), le rouvrir depuis l'écran d'accueil, revenir
   sur l'écran : la valeur modifiée est là, les autres sont inchangées.

**Jeu** veut dire : **Build and play in Dolphin** (Disc & Patch), ou **Play in Dolphin…** sur la page du
chapitre, puis vérifier la modification à l'écran.

## 0. Préparation (15 min)

- [ ] Télécharger l'artefact `windows-release` du dernier run CI vert de `main` (version 1.0.0.0),
      l'extraire dans un **nouveau** dossier hors de `Program Files`.
- [ ] Lancer `TelliusModding.exe` : la fenêtre s'ouvre. Le nom du ZIP indique 1.0.0.0 (l'app n'affiche sa version nulle part dans l'interface).
- [ ] Premier lancement : **Download missing tools** installe WIT (et FFmpeg) sans erreur.
- [ ] **Settings ▸ Preferences** : Dolphin est trouvé ; le thème clair/sombre change bien.
- [ ] Sauvegarder le dossier de saves Dolphin de RD
      (`%APPDATA%\Dolphin Emulator\Wii\title\00010000\52464545\data`) et une copie des `.gci` POR.
- [ ] Travailler sur des **projets neufs** (étape 1), pas sur les projets de développement.

## 1. Création de projet et disque (20 min, les deux jeux)

- [ ] ⭐ **New project** POR US (`GFEE01`) depuis l'ISO : l'extraction finit, Home montre toutes les sections.
- [ ] ⭐ **New project** RD US (`RFEE01`) depuis le WBFS/ISO : idem.
- [ ] Un projet RD EU (`RFEP01`) ou JP (`RFEJ01`) s'ouvre et s'extrait (un seul suffit).
- [ ] ⭐ **Tools ▸ Check** sur chaque projet neuf : aucune erreur (POR : 4 avertissements attendus des données retail).
- [ ] ⭐ **Build disc** sans modification sur chaque jeu, puis **Build and play in Dolphin** :
      le jeu démarre jusqu'à l'écran titre et une nouvelle partie se lance.
- [ ] **Search everything… Ctrl+K** : taper « Ike », ouvrir sa page personnage. Breadcrumbs et **Alt+←/→** fonctionnent.

## 2. Personnages et Game Data (35 min)

Sur chaque jeu, le cycle **M/S/R** :

- [ ] ⭐ **Characters ▸ Ike ▸ Stats** : +2 en Force de base, **Save**. **Jeu** (POR ch.1 / RD 1-1 avec Micaiah) : la stat change.
- [ ] ⭐ **Game Data ▸ Classes** : changer le mouvement d'une classe jouée au premier chapitre. **Jeu** : la portée de déplacement change.
- [ ] **Game Data ▸ Items** : Might de l'Iron Sword +5. M/S/R, puis la prévision de combat en jeu.
- [ ] **Game Data ▸ Skills** et **Terrain** : M/S/R sur un champ chacun.
- [ ] **Game Data ▸ General** : M/S/R sur une constante de difficulté.
- [ ] **New…** puis **Remove** d'un objet copié : la suppression est acceptée, **Check** reste propre.
- [ ] **Export Excel…** / **Import Excel…** : modifier une cellule dans Excel, réimporter, la valeur suit (RD : déjà vérifié le 2026-10-28, refaire une fois sur POR).
- [ ] ⭐ RD **Supports** : ajouter une affinité ou un bonus de lien, M/S/R. (Non testé en jeu à ce jour : nécessite une save de la partie 3, sinon noter « non vérifié ».)
- [ ] POR **Supports** : ajouter un partenaire, ouvrir **Conversation C**, M/S/R.
- [ ] **Colour variant…** sur un personnage : la variante est créée, visible dans **Portraits** et en jeu.

## 3. Chapitres (45 min)

Sur POR ch.1 (`01`) et RD 1-1 :

- [ ] ⭐ **Build** : déplacer une unité de 2 cases, peindre une case de Thicket (pas Forest), **Save Chapter**, **Jeu** : l'unité et le terrain ont bougé.
- [ ] **Build ▸ Tile heights** et **Place prop** : M/S/R ; **Undo/Redo** (Ctrl+Z / Ctrl+Y) annulent bien.
- [ ] **Deployment** : changer le niveau d'un ennemi en Normal, M/S/R.
- [ ] ⭐ **Dialogue** : modifier une ligne du premier message, l'aperçu se met à jour, **Save**, **Jeu** : la nouvelle ligne s'affiche. (RD : vérifier aussi que les portraits sont bien placés, l'aperçu RD n'a pas été comparé au jeu.)
- [ ] ⭐ **Script** : changer un argument simple (par ex. un `BGMPlay`), **Save** compile sans erreur, **Jeu** : l'effet est visible.
- [ ] **Shops** : ajouter un objet à l'Armory, **Copy to other difficulties**, M/S/R, **Jeu** sur un chapitre à base (POR ch.8 / RD 1-6).
- [ ] **Chapter data** : changer l'objectif (RD) ou la musique de carte (POR). **Jeu** : le nouveau texte / la nouvelle musique.
- [ ] RD : changer la météo du chapitre. **Jeu**. (Non confirmé le 2026-10-28 : noter ce qu'on voit.)
- [ ] **Battle scenes** : donner une ligne propre à la carte, changer la plaine. **Jeu** avec animations : le nouveau décor.
- [ ] ⭐ **Add chapter…** après le chapitre 1 / 1-1, **Jeu** : le chapitre ajouté se charge, puis l'histoire reprend.
- [ ] **Story order…** : faire sauter un chapitre, **Jeu** : le jeu enchaîne sur le bon chapitre ; remettre l'ordre.
- [ ] **Play…** (lecture dans l'app) : le chapitre se joue jusqu'au premier tour joueur, une attaque montre la prévision.

## 4. Assets (40 min)

M/S/R sur chaque éditeur, **Jeu** quand indiqué :

- [ ] ⭐ **Portraits** : **Replace picture…** sur un visage, **Jeu** : le portrait change en dialogue (RD : 4:3 et 16:9).
- [ ] **Icons** : **Replace icon…** sur une icône d'objet, puis **Restore original file**.
- [ ] **Fonts** (POR) : import d'une police TrueType, **Save**, **Jeu** : le texte reste sur ses lignes.
- [ ] ⭐ **3D Models** : **Export .glb...** puis **Import .glb...** du même modèle de carte : la fenêtre de revue s'ouvre, **Write files**, **Jeu** : le modèle s'affiche. **Restore original...** remet l'original.
- [ ] **Map Objects** : un prop s'affiche en 3D ; **Export .glb...** fonctionne.
- [ ] **Animation Data ▸ Edit…** : POR change un numéro de texture d'armée ; RD change l'octet de variante. **Jeu**.
- [ ] ⭐ **Battle Data** : RD **Edit fields…** sur une table `FE10Battle` (nouveau en 1.0) et **Motions by weapon…** ; POR **Form** sur `param.dbx`. M/S/R, **Jeu** avec animations : le combat se lance sans plantage.
- [ ] **Battle Weapons** : effet `EID_K_FIRE` sur l'Iron Sword, **Jeu** : l'effet de feu en combat.
- [ ] **Battle Sceneries**, **Battle Cameras**, **Battle Unit Parameters** : M/S/R puis **Restore original**.
- [ ] **Visual Effects** et éditeur de particules : modifier un émetteur, **Jeu** : le sort s'affiche. Ajout puis **Remove added effect**.
- [ ] ⭐ RD **Sound Tables** (nouveau en 1.0) : changer la musique d'un chapitre (Chapter music) et le volume d'un cue, M/S/R, **Jeu** : la nouvelle musique ; ajouter puis supprimer une ligne.
- [ ] **Music** : **New track…** depuis un WAV, l'assigner à un chapitre, **Jeu** : la piste joue (un nouveau cue BGM n'a jamais été vérifié dans Dolphin).
- [ ] **Sound Effects** : **Replace audio…** sur un cue de menu, **Jeu**.
- [ ] **Videos** : **Replace** d'une courte vidéo, **Jeu** : elle joue avec le son (l'audio est maintenant ajusté à la durée de la vidéo).
- [ ] **Tutorials**, **Staff Credits**, **Soundroom Images/Tracks** : M/S/R.
- [ ] RD : **Glossary**, **Conversation Room**, **Endings**, **Class Introductions**, **Movie Subtitles**, **World Map Routes**, **Wii Banner** : chacun s'ouvre, M/S/R sur une valeur. **Jeu** pour le **Wii Banner** (menu Wii de Dolphin).
- [ ] **Backgrounds** : **Add New Background...**, l'utiliser dans un message, **Jeu**.

## 5. Outils (30 min)

- [ ] ⭐ **Tools ▸ Game Code** : un réglage de combat (par ex. multiplicateur de critique) et l'activation d'une compétence à 4x. **Jeu** : effet visible. **Reset everything** remet tout.
- [ ] RD **Level-up growth** : gain de PV par réussite à 3, monter un niveau. (Laissé à une personne le 2026-10-28.)
- [ ] ⭐ **Tools ▸ Saves** POR : ouvrir un `.gci`, changer le niveau d'une unité, **Save as…**, **Play in Dolphin…** : la save charge.
- [ ] ⭐ **Tools ▸ Saves** RD : ouvrir une copie de `FE10_US.dat`, mettre une Iron Sword dans le convoi et changer un objet d'une unité, **Save**, **Play in Dolphin…** : pas de message de corruption. (Convoi RD non testé à ce jour.)
- [ ] **Flags** (Game Data) : renommer un drapeau réservé, puis **Save file** sur une save : bascule d'un drapeau, la save charge.
- [ ] **AI (CP)** : M/S/R sur une valeur d'IA.
- [ ] **Battle Simulator** : deux unités, **Render fight** joue le combat.

## 6. Partage et texte (20 min)

- [ ] ⭐ **Mod details**, puis **Create patch…** sur le projet modifié de chaque jeu.
- [ ] ⭐ `TelliusPatcher.exe` (dans le ZIP) sur une **ISO vierge** + le `.tpatch` : l'image produite démarre dans Dolphin avec les modifications.
- [ ] **Apply patch…** dans l'app sur un projet neuf : mêmes modifications.
- [ ] RD : **Export for Riivolution…** (Disc & Patch), lancer le disque vierge avec Riivolution dans Dolphin : les modifications apparaissent.
- [ ] **Export as text…** dans un dossier vide : les dossiers et le marqueur `.tellius_text_export` sont créés ; un second export remplace le premier.

## 7. Documentation (10 min)

- [ ] Le site https://klg-tellius.github.io/TelliusModding/ s'ouvre, la page **What You Can Edit** correspond à ce qui a été vu ci-dessus.
- [ ] `START-HERE.txt` du ZIP : liens valides, licence MIT mentionnée.
- [ ] `release/RELEASE-NOTES.md` : première ligne `# Tellius Modding v1.0.0.0`, pas de fonctionnalité annoncée qu'on n'a pas vue marcher.

## Résultat

| Section | POR | RD | Remarques |
| --- | --- | --- | --- |
| 0. Préparation | | | |
| 1. Projet et disque | | | |
| 2. Personnages et Game Data | | | |
| 3. Chapitres | | | |
| 4. Assets | | | |
| 5. Outils | | | |
| 6. Partage et texte | | | |
| 7. Documentation | | | |

Go si toutes les lignes ⭐ passent sur les deux jeux. Un échec hors ⭐ peut aller dans
`docs/app/known-bugs.md` et les limites connues plutôt que bloquer la release.
