# Adjudication à l'aveugle de 74 demandes de pharmacocinétique

## Ton rôle

Tu es un expert en pharmacocinétique (analyse non compartimentale, NCA) qui sert d'annotateur. Un petit modèle de décision doit lire, pour chaque
demande d'un utilisateur, un état (ce que l'utilisateur a écrit, un extrait du tableau de données, les analyses déjà faites) et répondre à 20 questions
fermées. Un humain veut établir la réponse **correcte** à ces 20 questions pour 74 demandes, afin de mesurer ce modèle sur un jeu de test gelé.

Un relecteur indépendant a déjà proposé des réponses. Tu ne les vois pas et tu ne dois pas essayer de les deviner. Tu es l'un des deux adjudicateurs
indépendants : applique les définitions ci-dessous à la lettre, décide toi-même, et signale les cas où deux réponses sont défendables.

Ne te sers que de ce qui est écrit pour chaque demande (le message de l'utilisateur, l'extrait de tableau, les notes, les analyses du projet). Tu n'as
aucune autre information sur les données : en particulier, la voie d'administration ne se lit **pas** sur la forme de la courbe.

## Les 20 questions

Chaque demande reçoit une réponse à 7 champs : `analysis`, `route`, `auc_method`, `dose_has_unit`, `is_not_available`, `compare_pair`, et `asked`
(une liste qui résume 14 questions oui/non, une par paramètre). 6 + 14 = 20 questions.

### 1. `analysis` : quel calcul la dernière demande exige-t-elle, compte tenu des analyses déjà dans le projet ?

| valeur | sens |
|---|---|
| `nca` | lancer une **nouvelle** NCA sur les données importées (typiquement la première demande de la conversation qui réclame des paramètres NCA) |
| `fit_pk1` | ajuster un modèle à un compartiment |
| `fit_pk2` | ajuster un modèle à deux compartiments |
| `simulate` | simuler un profil de concentrations à partir d'un modèle déjà ajusté |
| `compare` | comparer deux analyses du projet (la seconde est lancée pour cette demande si elle n'existe pas encore) |
| `none_needed` | aucun nouveau calcul : on répond à partir des analyses déjà dans le projet ou de ce que l'utilisateur a dit. Cela couvre toute question sur un résultat déjà calculé, le rappel de la dose ou de la méthode, et aussi la demande d'un paramètre que Caladrius ne calcule pas pour la voie (le refus ne calcule rien) |
| `not_supported` | quelque chose que le système ne sait pas faire : bioéquivalence, modèle de population, état d'équilibre ou doses répétées, données urinaires, une explication rédigée, un graphique, un paramètre qui ne fait pas partie des 14 de la liste ci-dessous |

### 2. `route` : quelle voie d'administration l'utilisateur a-t-il **indiquée** pour la dose ?

`iv_bolus` (injection intraveineuse directe, bolus), `iv_infusion` (perfusion), `oral` (prise orale : comprimé, avalé, ingéré, per os, voie orale...),
`unknown` (le texte de l'utilisateur ne donne pas la voie, ni explicitement ni par un mot qui l'implique). La voie se lit dans les mots de
l'utilisateur (le message, ou son premier message pour un tour ultérieur), jamais dans les chiffres du tableau. Une dose répétée ou un recueil
urinaire sans voie écrite donne `unknown`.

### 3. `auc_method` : quelle méthode d'intégration de l'AUC la dernière demande précise-t-elle ou exige-t-elle pour que l'analyse tourne ?

- `linear` : règle des trapèzes linéaires ;
- `lin_up_log_down` : linéaire à la montée, logarithmique à la descente ;
- `not_applicable` : la demande ne nomme aucune méthode et ne lance aucune NCA.

Convention du projet. Si la demande **lance une NCA** (champ `analysis` = `nca`), la méthode est celle que la demande nomme ; si elle n'en nomme aucune,
c'est `linear` (la méthode dont l'analyse a besoin pour tourner). Si la demande relance l'analyse avec une autre méthode pour la comparer à la première
(`analysis` = `compare` avec relance), c'est la méthode de la nouvelle analyse. Dans tous les autres cas (lecture d'un résultat déjà calculé, rappel, refus,
ajustement, simulation, hors périmètre), la demande ne lance aucune NCA : `not_applicable`. Si ta lecture de ces règles laisse deux réponses défendables,
choisis-en une et signale-le dans `reason`.

### 4. `dose_has_unit` : la dose citée par l'utilisateur porte-t-elle une unité ?

`true` si la dose est écrite avec une unité de dose (mg, g, µg, mcg, ug, ...), même différente de celle des données ; `false` si le nombre est écrit
seul, sans unité, ou si aucune dose n'est donnée. Pour un tour ultérieur, c'est la dose du premier message de la conversation qui compte.

### 5. `is_not_available` : la dernière demande réclame-t-elle un paramètre que Caladrius ne calcule pas pour la voie indiquée ?

Caladrius calcule tous les paramètres de la liste de la question 7, sauf :
- `c0` après une prise **orale** ou une **perfusion** (il existe pour un bolus IV) ;
- `tlag` après une administration **intraveineuse**, bolus ou perfusion (il existe pour la voie orale).

`is_not_available` vaut `true` seulement si la demande réclame l'un de ces paramètres pour la voie indiquée (même s'il est demandé avec d'autres
paramètres qui sont, eux, calculés). Sinon `false`. Une demande hors périmètre (question 1, `not_supported`) n'est **pas** un paramètre non disponible :
`false`.

### 6. `compare_pair` : quelles deux analyses du projet la demande veut-elle comparer, et dans quel ordre ?

Valeurs : `not_applicable` (la demande ne compare aucune analyse), ou une clé `a+b` (a = l'analyse de référence, la comparaison est b moins a), ou
`none_available` (moins de deux analyses existent dans le projet, donc aucune paire ne peut être désignée). Les valeurs possibles sont rappelées pour
chaque demande ; tu dois en choisir une. Si l'ordre ou la paire n'est pas clairement dit, choisis la lecture la plus naturelle et signale-le.

### 7. `asked` : la liste des paramètres que la dernière demande réclame

Clés autorisées (14) et ce qu'elles désignent :

| clé | paramètre |
|---|---|
| `cmax` | concentration maximale (Cmax, « le pic ») |
| `tmax` | temps du maximum (Tmax) |
| `c0` | concentration initiale extrapolée (C0) |
| `auclast` | AUC jusqu'au dernier point, AUC(0-tlast) (AUC0-t, AUC(0-t), « l'aire jusqu'au dernier prélèvement ») |
| `aucinf` | AUC extrapolée à l'infini, AUC(0-inf) (AUC0-∞) |
| `lambda_z` | constante de vitesse terminale (λz) |
| `half_life` | demi-vie terminale (t1/2, t½) |
| `cl` | clairance (CL, ou CL/F, même écrit après une injection IV) |
| `vz` | volume de distribution (Vz, Vz/F, Vd, même écrit après une injection IV) |
| `mrt` | temps moyen de résidence (MRT) |
| `aucpext` | pourcentage de l'AUC extrapolée à l'infini (% extrapolé) |
| `lambda_z_points` | nombre de points de la régression terminale de λz |
| `adj_r2` | R² ajusté de la régression terminale de λz |
| `tlag` | temps de latence (Tlag) |

Règles : on ne met dans `asked` que ce que la **dernière demande** réclame. Un paramètre nié (« pas l'AUC, seulement la demi-vie ») ou corrigé
(« la Cmax... non, le Tmax ») n'est pas demandé. `asked` est `[]` pour un rappel, un ajustement, une simulation, une demande hors périmètre, et pour une
comparaison qui ne nomme aucun paramètre. Un paramètre qui ne fait pas partie des 14 (Vss, ka, Cmin...) n'a pas de clé : il n'apparaît pas dans `asked`
(et la demande relève alors de `not_supported`, question 1). Si la demande dit « l'AUC » sans préciser laquelle, choisis la lecture la plus naturelle
(`auclast`, `aucinf`, ou les deux) et signale-le dans `reason`.

## Format de ta réponse (strict)

Réponds uniquement par **74 lignes JSON** (JSON Lines) : une ligne par demande, dans l'ordre, sans titre, sans texte avant ou après, sans bloc de code,
sans tableau englobant. Chaque ligne est un objet JSON sur **une seule ligne**, avec exactement ces champs :

{"id": "ood-001", "analysis": "nca", "route": "oral", "auc_method": "linear", "dose_has_unit": true, "is_not_available": false, "compare_pair": "not_applicable", "asked": ["cmax", "tmax"], "reason": ""}

- `analysis` ∈ nca, fit_pk1, fit_pk2, simulate, compare, none_needed, not_supported ;
- `route` ∈ iv_bolus, iv_infusion, oral, unknown ;
- `auc_method` ∈ linear, lin_up_log_down, not_applicable ;
- `dose_has_unit` et `is_not_available` : les booléens JSON `true` ou `false` (sans guillemets) ;
- `compare_pair` : une des valeurs possibles listées pour la demande ;
- `asked` : une liste de clés parmi les 14 (liste vide `[]` si aucune), sans doublon ;
- `reason` : une phrase courte en français pour tout ce qui n'est pas évident (une convention appliquée, une ambiguïté, une lecture choisie), sinon la chaîne
  vide `""`. **Si deux réponses sont défendables pour un champ, commence `reason` par `AMBIGU :`, indique le champ, la réponse choisie et l'autre
  réponse possible.**

Les `id` doivent être exactement ceux de la liste ci-dessous. Ne saute aucune demande, n'en ajoute aucune. Les demandes sont indépendantes : chacune
est une conversation à part, avec son propre tableau.

## Les 74 demandes

Chaque bloc donne ce que le modèle de décision voit. Les numéros d'analyse sont ceux du projet de cette conversation.

### ood-001

Tour 1 : première demande de la conversation.
Message de l'utilisateur : « J'ai pris un comprimé de 400 mg ce matin, voici mes concentrations. C'est quoi le Cmax et le Tmax ? »
Tableau joint : 12 lignes, un sujet ; en-tête puis 5 premières lignes :

```
time (h),conc (ng/mL)
0,0
0.13,1300
0.22,1814
0.37,2965
0.61,3887
```

Analyses déjà dans le projet : aucune
`compare_pair` possibles : `not_applicable`, `none_available`

### ood-002

Tour 2.
Premier message de l'utilisateur (déjà envoyé, avec le tableau) : « Voici les données d'un exercice (400 mg par voie orale ; temps en h, concentration en ng/mL) : »
Tableau joint : 12 lignes, un sujet ; en-tête puis 5 premières lignes :

```
time (h),conc (ng/mL)
0,0
0.13,1300
0.22,1814
0.37,2965
0.61,3887
```

Analyses déjà dans le projet : n°1 (NCA, AUC linéaire)
Dernière demande de l'utilisateur : « et la t1/2 stp ? »
`compare_pair` possibles : `not_applicable`, `none_available`

### ood-003

Tour 2.
Premier message de l'utilisateur (déjà envoyé, avec le tableau) : « Voici les données d'un exercice (400 mg par voie orale ; temps en h, concentration en ng/mL) : »
Tableau joint : 12 lignes, un sujet ; en-tête puis 5 premières lignes :

```
time (h),conc (ng/mL)
0,0
0.13,1300
0.22,1814
0.37,2965
0.61,3887
```

Analyses déjà dans le projet : n°1 (NCA, AUC linéaire)
Dernière demande de l'utilisateur : « AUC0-t et AUC0-inf svp »
`compare_pair` possibles : `not_applicable`, `none_available`

### ood-004

Tour 1 : première demande de la conversation.
Message de l'utilisateur : « bolus IV de 200 mg ; quel est le Vd ? »
Tableau joint : 9 lignes, un sujet ; en-tête puis 5 premières lignes :

```
time (h),conc (mg/L)
2.7,3.679
3.9,3.404
5.7,2.898
8.2,2.942
12,2.073
```

Analyses déjà dans le projet : aucune
`compare_pair` possibles : `not_applicable`, `none_available`

### ood-005

Tour 1 : première demande de la conversation.
Message de l'utilisateur : « bolus de 200 mg : Cl/F ? »
Tableau joint : 9 lignes, un sujet ; en-tête puis 5 premières lignes :

```
time (h),conc (mg/L)
2.7,3.679
3.9,3.404
5.7,2.898
8.2,2.942
12,2.073
```

Analyses déjà dans le projet : aucune
`compare_pair` possibles : `not_applicable`, `none_available`

### ood-006

Tour 1 : première demande de la conversation.
Message de l'utilisateur : « Ajuste un modèle à deux compartiments après un bolus IV de 300 mg. »
Tableau joint : 11 lignes, un sujet ; en-tête puis 5 premières lignes :

```
time (h),conc (mg/L)
0.75,8.391
1.2,7.543
1.9,6.771
3.1,5.418
5,4.441
```

Analyses déjà dans le projet : aucune
`compare_pair` possibles : `not_applicable`, `none_available`

### ood-007

Tour 1 : première demande de la conversation.
Message de l'utilisateur : « fit un modèle mono-compartiment sur ces données (bolus de 300 mg) »
Tableau joint : 11 lignes, un sujet ; en-tête puis 5 premières lignes :

```
time (h),conc (mg/L)
0.75,8.391
1.2,7.543
1.9,6.771
3.1,5.418
5,4.441
```

Analyses déjà dans le projet : aucune
`compare_pair` possibles : `not_applicable`, `none_available`

### ood-008

Tour 1 : première demande de la conversation.
Message de l'utilisateur : « Perfusion de 150 mg sur 2 h. Donne-moi le Cmax et l'AUC(0-t). »
Tableau joint : 10 lignes, un sujet ; en-tête puis 5 premières lignes :

```
time (h),conc (mg/L)
0,0
0.67,0.886
1,1.312
1.5,2.036
2,2.093
```

Analyses déjà dans le projet : aucune
`compare_pair` possibles : `not_applicable`, `none_available`

### ood-009

Tour 2.
Premier message de l'utilisateur (déjà envoyé, avec le tableau) : « Voici les données d'un exercice (150 mg en perfusion intraveineuse de 2 h ; temps en h, concentration en mg/L) : »
Tableau joint : 10 lignes, un sujet ; en-tête puis 5 premières lignes :

```
time (h),conc (mg/L)
0,0
0.67,0.886
1,1.312
1.5,2.036
2,2.093
```

Analyses déjà dans le projet : n°1 (NCA, AUC linéaire)
Dernière demande de l'utilisateur : « Et la MRT ? »
`compare_pair` possibles : `not_applicable`, `none_available`

### ood-010

Tour 1 : première demande de la conversation.
Message de l'utilisateur : « Perfusion de 500 µg pendant 1,5 h, Cmax et AUC0-inf. »
Tableau joint : 8 lignes, un sujet ; en-tête puis 5 premières lignes :

```
time (min),conc (ng/mL)
0,0
30,1.561
90,4.479
130,4.256
280,2.98
```

Analyses déjà dans le projet : aucune
`compare_pair` possibles : `not_applicable`, `none_available`

### ood-011

Tour 1 : première demande de la conversation.
Message de l'utilisateur : « Perfusion de 500 µg pendant 90 minutes : que vaut l'AUC(0-t) ? »
Tableau joint : 8 lignes, un sujet ; en-tête puis 5 premières lignes :

```
time (min),conc (ng/mL)
0,0
30,1.561
90,4.479
130,4.256
280,2.98
```

Analyses déjà dans le projet : aucune
`compare_pair` possibles : `not_applicable`, `none_available`

### ood-012

Tour 1 : première demande de la conversation.
Message de l'utilisateur : « J'ai avalé 800 µg, les temps sont en minutes ; Cmax et AUC0-t. »
Tableau joint : 8 lignes, un sujet ; en-tête puis 5 premières lignes :

```
time (min),conc (ng/mL)
0,0
16,8.674
38,17.72
91,32.81
220,39.91
```

Analyses déjà dans le projet : aucune
`compare_pair` possibles : `not_applicable`, `none_available`

### ood-013

Tour 2.
Premier message de l'utilisateur (déjà envoyé, avec le tableau) : « Voici les données d'un exercice (800 µg par voie orale ; temps en min, concentration en ng/mL) : »
Tableau joint : 8 lignes, un sujet ; en-tête puis 5 premières lignes :

```
time (min),conc (ng/mL)
0,0
16,8.674
38,17.72
91,32.81
220,39.91
```

Analyses déjà dans le projet : n°1 (NCA, AUC linéaire)
Dernière demande de l'utilisateur : « Compare l'AUC linéaire et la lin-up/log-down. »
`compare_pair` possibles : `not_applicable`, `none_available`

### ood-014

Tour 2.
Premier message de l'utilisateur (déjà envoyé, avec le tableau) : « Voici les données d'un exercice (800 µg par voie orale ; temps en min, concentration en ng/mL) : »
Tableau joint : 8 lignes, un sujet ; en-tête puis 5 premières lignes :

```
time (min),conc (ng/mL)
0,0
16,8.674
38,17.72
91,32.81
220,39.91
```

Analyses déjà dans le projet : n°1 (NCA, AUC linéaire) ; n°2 (NCA, AUC lin-up/log-down)
Dernière demande de l'utilisateur : « Compare les deux AUC (valeur et %). »
`compare_pair` possibles : `not_applicable`, `1+2`, `2+1`

### ood-015

Tour 2.
Premier message de l'utilisateur (déjà envoyé, avec le tableau) : « Voici les données d'un exercice (800 µg par voie orale ; temps en min, concentration en ng/mL) : »
Tableau joint : 8 lignes, un sujet ; en-tête puis 5 premières lignes :

```
time (min),conc (ng/mL)
0,0
16,8.674
38,17.72
91,32.81
220,39.91
```

Analyses déjà dans le projet : n°1 (NCA, AUC linéaire) ; n°2 (NCA, AUC lin-up/log-down)
Dernière demande de l'utilisateur : « Compare l'analyse 2 à l'analyse 1. »
`compare_pair` possibles : `not_applicable`, `1+2`, `2+1`

### ood-016

Tour 1 : première demande de la conversation.
Message de l'utilisateur : « Voie orale, 300 mg : y a-t-il un Tlag ? »
Tableau joint : 8 lignes, un sujet ; en-tête puis 5 premières lignes :

```
time (h),conc (ng/mL)
0,0
0.39,0
0.79,1801
1.6,4902
3.2,7305
```

Analyses déjà dans le projet : aucune
`compare_pair` possibles : `not_applicable`, `none_available`

### ood-017

Tour 1 : première demande de la conversation.
Message de l'utilisateur : « Quel est le Tlag de ce bolus de 200 mg ? »
Tableau joint : 9 lignes, un sujet ; en-tête puis 5 premières lignes :

```
time (h),conc (mg/L)
2.7,3.679
3.9,3.404
5.7,2.898
8.2,2.942
12,2.073
```

Analyses déjà dans le projet : aucune
`compare_pair` possibles : `not_applicable`, `none_available`

### ood-018

Tour 1 : première demande de la conversation.
Message de l'utilisateur : « Quelle est la C0 après cette prise orale de 400 mg ? »
Tableau joint : 12 lignes, un sujet ; en-tête puis 5 premières lignes :

```
time (h),conc (ng/mL)
0,0
0.13,1300
0.22,1814
0.37,2965
0.61,3887
```

Analyses déjà dans le projet : aucune
`compare_pair` possibles : `not_applicable`, `none_available`

### ood-019

Tour 1 : première demande de la conversation.
Message de l'utilisateur : « Ce produit de 400 mg est-il bioéquivalent au princeps ? »
Tableau joint : 12 lignes, un sujet ; en-tête puis 5 premières lignes :

```
time (h),conc (ng/mL)
0,0
0.13,1300
0.22,1814
0.37,2965
0.61,3887
```

Analyses déjà dans le projet : aucune
`compare_pair` possibles : `not_applicable`, `none_available`

### ood-020

Tour 1 : première demande de la conversation.
Message de l'utilisateur : « Estime un modèle de population à effets mixtes (NONMEM) sur ces données, dose 400 mg. »
Tableau joint : 12 lignes, un sujet ; en-tête puis 5 premières lignes :

```
time (h),conc (ng/mL)
0,0
0.13,1300
0.22,1814
0.37,2965
0.61,3887
```

Analyses déjà dans le projet : aucune
`compare_pair` possibles : `not_applicable`, `none_available`

### ood-021

Tour 1 : première demande de la conversation.
Message de l'utilisateur : « Après une prise orale, voici mes concentrations : quelle est la demi-vie ? »
Tableau joint : 11 lignes, un sujet ; en-tête puis 5 premières lignes :

```
time (h),conc (ng/mL)
0,0
0.25,182.6
0.39,300.4
0.61,439.5
0.95,595.7
```

Analyses déjà dans le projet : aucune
`compare_pair` possibles : `not_applicable`, `none_available`

### ood-022

Tour 1 : première demande de la conversation.
Message de l'utilisateur : « Prise orale de 100, voici les données. Cmax ? »
Tableau joint : 11 lignes, un sujet ; en-tête puis 5 premières lignes :

```
time (h),conc (ng/mL)
0,0
0.25,182.6
0.39,300.4
0.61,439.5
0.95,595.7
```

Analyses déjà dans le projet : aucune
`compare_pair` possibles : `not_applicable`, `none_available`

### ood-023

Tour 1 : première demande de la conversation.
Message de l'utilisateur : « Bolus IV de 2 mg : donne-moi la clairance et le Vz. »
Tableau joint : 11 lignes, un sujet ; en-tête puis 5 premières lignes :

```
time (h),conc (ng/mL)
1.2,23.93
1.6,22.66
2.3,16.16
3.2,16.5
4.4,13.81
```

Note ajoutée au tableau : Les valeurs égales à 0 sont sous la limite de quantification (LLOQ = 0,72 ng/mL).
Analyses déjà dans le projet : aucune
`compare_pair` possibles : `not_applicable`, `none_available`

### ood-024

Tour 1 : première demande de la conversation.
Message de l'utilisateur : « Bolus de 2000 mcg : CL et Vz. »
Tableau joint : 11 lignes, un sujet ; en-tête puis 5 premières lignes :

```
time (h),conc (ng/mL)
1.2,23.93
1.6,22.66
2.3,16.16
3.2,16.5
4.4,13.81
```

Note ajoutée au tableau : Les valeurs égales à 0 sont sous la limite de quantification (LLOQ = 0,72 ng/mL).
Analyses déjà dans le projet : aucune
`compare_pair` possibles : `not_applicable`, `none_available`

### ood-025

Tour 2.
Premier message de l'utilisateur (déjà envoyé, avec le tableau) : « Voici les données d'un exercice (2000 µg en bolus intraveineux ; temps en h, concentration en ng/mL) : »
Tableau joint : 11 lignes, un sujet ; en-tête puis 5 premières lignes :

```
time (h),conc (ng/mL)
1.2,23.93
1.6,22.66
2.3,16.16
3.2,16.5
4.4,13.81
```

Note ajoutée au tableau : Les valeurs égales à 0 sont sous la limite de quantification (LLOQ = 0,72 ng/mL).
Analyses déjà dans le projet : n°1 (NCA, AUC linéaire)
Dernière demande de l'utilisateur : « Et le pourcentage d'AUC extrapolée ? »
`compare_pair` possibles : `not_applicable`, `none_available`

### ood-026

Tour 1 : première demande de la conversation.
Message de l'utilisateur : « Il y a un zéro sous la LLOQ dans le tableau, on le garde ? Donne l'AUC(0-t) et la Cmax, dose orale 50 mg. »
Tableau joint : 11 lignes, un sujet ; en-tête puis 5 premières lignes :

```
time (h),conc (ng/mL)
0,0
0.11,62.73
0.2,120.4
0.36,168.2
0.64,246.8
```

Note ajoutée au tableau : Les valeurs égales à 0 sont sous la limite de quantification (LLOQ = 13 ng/mL).
Analyses déjà dans le projet : aucune
`compare_pair` possibles : `not_applicable`, `none_available`

### ood-027

Tour 1 : première demande de la conversation.
Message de l'utilisateur : « Simule les concentrations après une dose orale de 300 mg. »
Tableau joint : 8 lignes, un sujet ; en-tête puis 5 premières lignes :

```
time (h),conc (ng/mL)
0,0
0.14,1312
0.35,2720
0.84,5269
2,4654
```

Analyses déjà dans le projet : aucune
`compare_pair` possibles : `not_applicable`, `none_available`

### ood-028

Tour 1 : première demande de la conversation.
Message de l'utilisateur : « Donne-moi d'abord la demi-vie, ensuite la clairance et le Vz, pour cette dose orale de 300 mg. »
Tableau joint : 8 lignes, un sujet ; en-tête puis 5 premières lignes :

```
time (h),conc (ng/mL)
0,0
0.14,1312
0.35,2720
0.84,5269
2,4654
```

Analyses déjà dans le projet : aucune
`compare_pair` possibles : `not_applicable`, `none_available`

### ood-029

Tour 1 : première demande de la conversation.
Message de l'utilisateur : « Donne-moi le Cmax puis refais l'analyse en lin-up/log-down, bolus de 300 mg. »
Tableau joint : 11 lignes, un sujet ; en-tête puis 5 premières lignes :

```
time (h),conc (mg/L)
0.75,8.391
1.2,7.543
1.9,6.771
3.1,5.418
5,4.441
```

Analyses déjà dans le projet : aucune
`compare_pair` possibles : `not_applicable`, `none_available`

### ood-030

Tour 2.
Premier message de l'utilisateur (déjà envoyé, avec le tableau) : « Voici les données d'un exercice (300 mg en bolus intraveineux ; temps en h, concentration en mg/L) : »
Tableau joint : 11 lignes, un sujet ; en-tête puis 5 premières lignes :

```
time (h),conc (mg/L)
0.75,8.391
1.2,7.543
1.9,6.771
3.1,5.418
5,4.441
```

Analyses déjà dans le projet : n°1 (NCA, AUC linéaire)
Dernière demande de l'utilisateur : « Refais l'analyse en lin-up/log-down et compare les deux AUC en valeur et en %. »
`compare_pair` possibles : `not_applicable`, `none_available`

### ood-031

Tour 1 : première demande de la conversation.
Message de l'utilisateur : « Peux-tu me donner le Cmax, le Tmax et le t1/2 after a single oral dose of 100 mg ? »
Tableau joint : 12 lignes, un sujet ; en-tête puis 5 premières lignes :

```
time (h),conc (mg/L)
0,0
0.51,0
0.75,0
1.1,0.8048
1.6,1.655
```

Analyses déjà dans le projet : aucune
`compare_pair` possibles : `not_applicable`, `none_available`

### ood-032

Tour 1 : première demande de la conversation.
Message de l'utilisateur : « kel est le Cmax é le Tmax de ce tablo ? dose 400 mg per os »
Tableau joint : 12 lignes, un sujet ; en-tête puis 5 premières lignes :

```
time (h),conc (ng/mL)
0,0
0.13,1300
0.22,1814
0.37,2965
0.61,3887
```

Analyses déjà dans le projet : aucune
`compare_pair` possibles : `not_applicable`, `none_available`

### ood-033

Tour 1 : première demande de la conversation.
Message de l'utilisateur : « Dose orale de 500 mg : AUC0-∞ et AUC0-t. »
Tableau joint : 10 lignes, un sujet ; en-tête puis 5 premières lignes :

```
time (h),conc (mg/L)
0,0
0.3,0.9396
0.59,1.736
1.1,2.39
2.2,3.817
```

Analyses déjà dans le projet : aucune
`compare_pair` possibles : `not_applicable`, `none_available`

### ood-034

Tour 1 : première demande de la conversation.
Message de l'utilisateur : « Bolus de 150 mg : quel est le Vdss ? »
Tableau joint : 12 lignes, un sujet ; en-tête puis 5 premières lignes :

```
time (h),conc (ng/mL)
1.2,2742
1.6,3020
2.1,2558
2.8,2539
3.6,2143
```

Analyses déjà dans le projet : aucune
`compare_pair` possibles : `not_applicable`, `none_available`

### ood-035

Tour 1 : première demande de la conversation.
Message de l'utilisateur : « Bolus de 150 mg : le R² ajusté et le nombre de points de la régression terminale. »
Tableau joint : 12 lignes, un sujet ; en-tête puis 5 premières lignes :

```
time (h),conc (ng/mL)
1.2,2742
1.6,3020
2.1,2558
2.8,2539
3.6,2143
```

Analyses déjà dans le projet : aucune
`compare_pair` possibles : `not_applicable`, `none_available`

### ood-036

Tour 1 : première demande de la conversation.
Message de l'utilisateur : « Prise unique de 100 mg par voie orale : je veux le MRT et la demi-vie. »
Tableau joint : 10 lignes, un sujet ; en-tête puis 5 premières lignes :

```
time (h),conc (ng/mL)
0,0
0.22,174.3
0.42,347.9
0.82,553.1
1.6,825
```

Analyses déjà dans le projet : aucune
`compare_pair` possibles : `not_applicable`, `none_available`

### ood-037

Tour 1 : première demande de la conversation.
Message de l'utilisateur : « Perfusion de 150 mg sur 2 h : clairance et volume de distribution. »
Tableau joint : 10 lignes, un sujet ; en-tête puis 5 premières lignes :

```
time (h),conc (mg/L)
0,0
0.67,0.886
1,1.312
1.5,2.036
2,2.093
```

Analyses déjà dans le projet : aucune
`compare_pair` possibles : `not_applicable`, `none_available`

### ood-038

Tour 1 : première demande de la conversation.
Message de l'utilisateur : « Quel est le Tlag de cette perfusion de 150 mg ? »
Tableau joint : 10 lignes, un sujet ; en-tête puis 5 premières lignes :

```
time (h),conc (mg/L)
0,0
0.67,0.886
1,1.312
1.5,2.036
2,2.093
```

Analyses déjà dans le projet : aucune
`compare_pair` possibles : `not_applicable`, `none_available`

### ood-039

Tour 1 : première demande de la conversation.
Message de l'utilisateur : « Dose IV de 1000 µg : AUC(0-inf) et pourcentage extrapolé. »
Tableau joint : 9 lignes, un sujet ; en-tête puis 5 premières lignes :

```
time (h),conc (ng/mL)
0.26,55.53
0.49,40.99
0.94,23.8
1.8,11.69
3.4,3.844
```

Analyses déjà dans le projet : aucune
`compare_pair` possibles : `not_applicable`, `none_available`

### ood-040

Tour 1 : première demande de la conversation.
Message de l'utilisateur : « J'ai ingéré 2000 µg : au bout de combien de temps la concentration est-elle divisée par deux ? »
Tableau joint : 11 lignes, un sujet ; en-tête puis 5 premières lignes :

```
time (h),conc (ng/mL)
0,0
0.4,10.19
0.71,20.02
1.3,26.64
2.3,30.69
```

Analyses déjà dans le projet : aucune
`compare_pair` possibles : `not_applicable`, `none_available`

### ood-041

Tour 1 : première demande de la conversation.
Message de l'utilisateur : « Bolus de 200 mg à t=0, temps en minutes : Cmax et Tmax. »
Tableau joint : 12 lignes, un sujet ; en-tête puis 5 premières lignes :

```
time (min),conc (ng/mL)
19,7078
30,5478
47,4806
74,3421
120,2138
```

Analyses déjà dans le projet : aucune
`compare_pair` possibles : `not_applicable`, `none_available`

### ood-042

Tour 1 : première demande de la conversation.
Message de l'utilisateur : « Ajuste un bi-exponentiel sur ces données (bolus de 200 mg). »
Tableau joint : 12 lignes, un sujet ; en-tête puis 5 premières lignes :

```
time (min),conc (ng/mL)
19,7078
30,5478
47,4806
74,3421
120,2138
```

Analyses déjà dans le projet : aucune
`compare_pair` possibles : `not_applicable`, `none_available`

### ood-043

Tour 1 : première demande de la conversation.
Message de l'utilisateur : « Perfusion IV de 150 mg sur 2 h, CL et Vz svp. »
Tableau joint : 8 lignes, un sujet ; en-tête puis 5 premières lignes :

```
time (h),conc (ng/mL)
0,0
0.67,704.1
2,2101
3,2078
6.3,1521
```

Analyses déjà dans le projet : aucune
`compare_pair` possibles : `not_applicable`, `none_available`

### ood-044

Tour 1 : première demande de la conversation.
Message de l'utilisateur : « Comprimé à libération prolongée de 5000 µg : Cmax, Tmax et demi-vie. »
Tableau joint : 8 lignes, un sujet ; en-tête puis 5 premières lignes :

```
time (h),conc (ng/mL)
0,0
0.38,15.76
0.83,33.16
1.8,61.61
4.1,49.61
```

Analyses déjà dans le projet : aucune
`compare_pair` possibles : `not_applicable`, `none_available`

### ood-045

Tour 1 : première demande de la conversation.
Message de l'utilisateur : « Bolus de 300 mg, temps en minutes : AUC(0-t) et clairance. »
Tableau joint : 9 lignes, un sujet ; en-tête puis 5 premières lignes :

```
time (min),conc (ng/mL)
130,2328
190,2424
270,2089
390,1993
570,1381
```

Analyses déjà dans le projet : aucune
`compare_pair` possibles : `not_applicable`, `none_available`

### ood-046

Tour 1 : première demande de la conversation.
Message de l'utilisateur : « Bolus de 150 mg : le Cl/F et le Vz/F ? »
Tableau joint : 12 lignes, un sujet ; en-tête puis 5 premières lignes :

```
time (h),conc (ng/mL)
0.67,3383
1,2987
1.7,2676
2.6,1906
4.1,1632
```

Analyses déjà dans le projet : aucune
`compare_pair` possibles : `not_applicable`, `none_available`

### ood-047

Tour 1 : première demande de la conversation.
Message de l'utilisateur : « Voie orale, 100 mg : λz et t½. »
Tableau joint : 10 lignes, un sujet ; en-tête puis 5 premières lignes :

```
time (h),conc (ng/mL)
0,0
0.22,174.3
0.42,347.9
0.82,553.1
1.6,825
```

Analyses déjà dans le projet : aucune
`compare_pair` possibles : `not_applicable`, `none_available`

### ood-048

Tour 1 : première demande de la conversation.
Message de l'utilisateur : « Voie orale, 300 mg : quelle est la constante d'absorption ka ? »
Tableau joint : 8 lignes, un sujet ; en-tête puis 5 premières lignes :

```
time (h),conc (ng/mL)
0,0
0.39,0
0.79,1801
1.6,4902
3.2,7305
```

Analyses déjà dans le projet : aucune
`compare_pair` possibles : `not_applicable`, `none_available`

### ood-049

Tour 1 : première demande de la conversation.
Message de l'utilisateur : « Cmax et nombre de points de la régression terminale, dose orale de 100 mg. »
Tableau joint : 11 lignes, un sujet ; en-tête puis 5 premières lignes :

```
time (h),conc (ng/mL)
0,0
0.25,182.6
0.39,300.4
0.61,439.5
0.95,595.7
```

Analyses déjà dans le projet : aucune
`compare_pair` possibles : `not_applicable`, `none_available`

### ood-050

Tour 1 : première demande de la conversation.
Message de l'utilisateur : « AUC(0-t) par la méthode lin-up/log-down, dose orale de 50 mg. »
Tableau joint : 11 lignes, un sujet ; en-tête puis 5 premières lignes :

```
time (h),conc (ng/mL)
0,0
0.11,62.73
0.2,120.4
0.36,168.2
0.64,246.8
```

Note ajoutée au tableau : Les valeurs égales à 0 sont sous la limite de quantification (LLOQ = 13 ng/mL).
Analyses déjà dans le projet : aucune
`compare_pair` possibles : `not_applicable`, `none_available`

### ood-051

Tour 1 : première demande de la conversation.
Message de l'utilisateur : « Bolus de 2000 µg : l'AUC(0-t) tient-elle compte du point sous la LLOQ ? et le % extrapolé ? »
Tableau joint : 11 lignes, un sujet ; en-tête puis 5 premières lignes :

```
time (h),conc (ng/mL)
1.2,23.93
1.6,22.66
2.3,16.16
3.2,16.5
4.4,13.81
```

Note ajoutée au tableau : Les valeurs égales à 0 sont sous la limite de quantification (LLOQ = 0,72 ng/mL).
Analyses déjà dans le projet : aucune
`compare_pair` possibles : `not_applicable`, `none_available`

### ood-052

Tour 1 : première demande de la conversation.
Message de l'utilisateur : « Dose orale de 500 mg, méthode des trapèzes linéaires : AUC0-t. »
Tableau joint : 12 lignes, un sujet ; en-tête puis 5 premières lignes :

```
time (h),conc (mg/L)
0,0
0.47,7.441
0.79,9.398
1.3,13.1
2.3,11.43
```

Analyses déjà dans le projet : aucune
`compare_pair` possibles : `not_applicable`, `none_available`

### ood-053

Tour 1 : première demande de la conversation.
Message de l'utilisateur : « Voici mes concentrations après 400 mg ; quel est le Cmax ? »
Tableau joint : 12 lignes, un sujet ; en-tête puis 5 premières lignes :

```
time (h),conc (ng/mL)
0,0
0.13,1300
0.22,1814
0.37,2965
0.61,3887
```

Analyses déjà dans le projet : aucune
`compare_pair` possibles : `not_applicable`, `none_available`

### ood-054

Tour 1 : première demande de la conversation.
Message de l'utilisateur : « Après une injection intraveineuse directe de 200 mg : C0 et Vz. »
Tableau joint : 9 lignes, un sujet ; en-tête puis 5 premières lignes :

```
time (h),conc (mg/L)
2.7,3.679
3.9,3.404
5.7,2.898
8.2,2.942
12,2.073
```

Analyses déjà dans le projet : aucune
`compare_pair` possibles : `not_applicable`, `none_available`

### ood-055

Tour 1 : première demande de la conversation.
Message de l'utilisateur : « Perfusion de 500 µg sur 90 min : Cmax. »
Tableau joint : 8 lignes, un sujet ; en-tête puis 5 premières lignes :

```
time (min),conc (ng/mL)
0,0
30,1.561
90,4.479
130,4.256
280,2.98
```

Analyses déjà dans le projet : aucune
`compare_pair` possibles : `not_applicable`, `none_available`

### ood-056

Tour 2.
Premier message de l'utilisateur (déjà envoyé, avec le tableau) : « Voici les données d'un exercice (400 mg par voie orale ; temps en h, concentration en ng/mL) : »
Tableau joint : 12 lignes, un sujet ; en-tête puis 5 premières lignes :

```
time (h),conc (ng/mL)
0,0
0.13,1300
0.22,1814
0.37,2965
0.61,3887
```

Analyses déjà dans le projet : n°1 (NCA, AUC linéaire)
Dernière demande de l'utilisateur : « Rappelle-moi la dose et la méthode d'AUC utilisées. »
`compare_pair` possibles : `not_applicable`, `none_available`

### ood-057

Tour 2.
Premier message de l'utilisateur (déjà envoyé, avec le tableau) : « Voici les données d'un exercice (300 mg en bolus intraveineux ; temps en h, concentration en mg/L) : »
Tableau joint : 11 lignes, un sujet ; en-tête puis 5 premières lignes :

```
time (h),conc (mg/L)
0.75,8.391
1.2,7.543
1.9,6.771
3.1,5.418
5,4.441
```

Analyses déjà dans le projet : n°1 (NCA, AUC linéaire) ; n°2 (NCA, AUC lin-up/log-down)
Dernière demande de l'utilisateur : « Compare le Cmax entre les deux méthodes. »
`compare_pair` possibles : `not_applicable`, `1+2`, `2+1`

### ood-058

Tour 1 : première demande de la conversation.
Message de l'utilisateur : « Compare les AUC linéaire et lin-up/log-down, dose orale de 400 mg. »
Tableau joint : 12 lignes, un sujet ; en-tête puis 5 premières lignes :

```
time (h),conc (ng/mL)
0,0
0.13,1300
0.22,1814
0.37,2965
0.61,3887
```

Analyses déjà dans le projet : aucune
`compare_pair` possibles : `not_applicable`, `none_available`

### ood-059

Tour 1 : première demande de la conversation.
Message de l'utilisateur : « 250 mg per os, voici les concentrations en µg/mL : Cmax, Tmax et AUC0-inf. »
Tableau joint : 10 lignes, un sujet ; en-tête puis 5 premières lignes :

```
time (h),conc (µg/mL)
0.5,2.3097
1,3.6496
1.5,4.3789
2,4.7259
3,4.8014
```

Analyses déjà dans le projet : aucune
`compare_pair` possibles : `not_applicable`, `none_available`

### ood-060

Tour 1 : première demande de la conversation.
Message de l'utilisateur : « Bolus IV de 120 mg : quel est le Tlag ? »
Tableau joint : 9 lignes, un sujet ; en-tête puis 5 premières lignes :

```
time (h),conc (mg/L)
0.25,5.2657
0.5,5.0835
1,4.7376
2,4.115
3,3.5741
```

Analyses déjà dans le projet : aucune
`compare_pair` possibles : `not_applicable`, `none_available`

### ood-061

Tour 1 : première demande de la conversation.
Message de l'utilisateur : « Quelle est la C0 après cette prise orale de 200 mg ? »
Tableau joint : 9 lignes, un sujet ; en-tête puis 5 premières lignes :

```
time (h),conc (ng/mL)
0.5,2044.7
1,3100.5
2,3768.2
3,3669.0
4,3352.2
```

Analyses déjà dans le projet : aucune
`compare_pair` possibles : `not_applicable`, `none_available`

### ood-062

Tour 1 : première demande de la conversation.
Message de l'utilisateur : « Perfusion de 75 mg sur 1,5 h, les temps sont en minutes : Cmax. »
Tableau joint : 8 lignes, un sujet ; en-tête puis 5 premières lignes :

```
time (min),conc (ng/mL)
15,131.97
30,138.54
60,138.89
90,138.89
120,0.34427
```

Analyses déjà dans le projet : aucune
`compare_pair` possibles : `not_applicable`, `none_available`

### ood-063

Tour 1 : première demande de la conversation.
Message de l'utilisateur : « Étude à deux sujets, 300 mg par voie orale : Cmax et AUC0-t par sujet. »
Tableau joint : 16 lignes, un sujet ; en-tête puis 5 premières lignes :

```
subject,time (h),conc (ng/mL)
1,0.5,2713.1
1,1,4186.7
1,2,5213.0
1,4,4717.4
1,6,3725.9
```

Analyses déjà dans le projet : aucune
`compare_pair` possibles : `not_applicable`, `none_available`

### ood-064

Tour 1 : première demande de la conversation.
Message de l'utilisateur : « Administration répétée de 100 mg toutes les 12 h : Cmax à l'état d'équilibre et Cmin. »
Tableau joint : 8 lignes, un sujet ; en-tête puis 5 premières lignes :

```
time (h),conc (ng/mL)
0.5,1450.1
1,1868.2
2,2113.5
4,1837.7
6,1437.1
```

Analyses déjà dans le projet : aucune
`compare_pair` possibles : `not_applicable`, `none_available`

### ood-065

Tour 1 : première demande de la conversation.
Message de l'utilisateur : « Recueil urinaire : quantité excrétée et clairance rénale. »
Tableau joint : 8 lignes, un sujet ; en-tête puis 5 premières lignes :

```
time (h),volume (mL),amount (mg)
0,0.0,0.0
1,160,2.34
2,200,4.16
4,240,5.26
6,280,5.93
```

Analyses déjà dans le projet : aucune
`compare_pair` possibles : `not_applicable`, `none_available`

### ood-066

Tour 1 : première demande de la conversation.
Message de l'utilisateur : « Ajuste un modèle à deux compartiments après 400 mg par voie orale. »
Tableau joint : 10 lignes, un sujet ; en-tête puis 5 premières lignes :

```
time (h),conc (ng/mL)
0.5,-55.705
1,258.44
2,887.73
3,1192.7
4,1262.1
```

Analyses déjà dans le projet : aucune
`compare_pair` possibles : `not_applicable`, `none_available`

### ood-067

Tour 1 : première demande de la conversation.
Message de l'utilisateur : « Voie orale 1200 mg, temps en minutes : t1/2 et MRT. »
Tableau joint : 10 lignes, un sujet ; en-tête puis 5 premières lignes :

```
time (min),conc (ng/mL)
30,436.23
60,6.5416
90,0.098095
120,0.001471
180,3.3078e-07
```

Analyses déjà dans le projet : aucune
`compare_pair` possibles : `not_applicable`, `none_available`

### ood-068

Tour 1 : première demande de la conversation.
Message de l'utilisateur : « 80 mg per os, il y a des zéros sous la LLOQ : AUC(0-t) et Cmax. »
Tableau joint : 10 lignes, un sujet ; en-tête puis 5 premières lignes :

```
time (h),conc (ng/mL)
0.5,1239.7
1,1834.6
2,2143.0
3,2024.2
4,1804.8
```

Note ajoutée au tableau : Les valeurs égales à 0 sont sous la limite de quantification (LLOQ = 1 ng/mL).
Analyses déjà dans le projet : aucune
`compare_pair` possibles : `not_applicable`, `none_available`

### ood-069

Tour 1 : première demande de la conversation.
Message de l'utilisateur : « J'ai pris 0,25 g par voie orale : Cmax et AUC0-t. »
Tableau joint : 8 lignes, un sujet ; en-tête puis 5 premières lignes :

```
time (h),conc (mg/L)
0.5,3.6562
1,5.6489
2,7.0537
4,6.427
6,5.1153
```

Analyses déjà dans le projet : aucune
`compare_pair` possibles : `not_applicable`, `none_available`

### ood-070

Tour 1 : première demande de la conversation.
Message de l'utilisateur : « Perfusion de 750 µg sur 1 h : Vz et CL. »
Tableau joint : 9 lignes, un sujet ; en-tête puis 5 premières lignes :

```
time (h),conc (ng/mL)
0.25,7.3886
0.5,14.559
0.75,21.517
1,28.27
1.5,26.624
```

Analyses déjà dans le projet : aucune
`compare_pair` possibles : `not_applicable`, `none_available`

### ood-071

Tour 2.
Premier message de l'utilisateur (déjà envoyé, avec le tableau) : « Voici les données d'un exercice (250 mg par voie orale ; temps en h, concentration en µg/mL) : »
Tableau joint : 10 lignes, un sujet ; en-tête puis 5 premières lignes :

```
time (h),conc (µg/mL)
0.5,2.3097
1,3.6496
1.5,4.3789
2,4.7259
3,4.8014
```

Analyses déjà dans le projet : n°1 (NCA, AUC linéaire)
Dernière demande de l'utilisateur : « Compare l'AUC linéaire et la lin-up/log-down. »
`compare_pair` possibles : `not_applicable`, `none_available`

### ood-072

Tour 2.
Premier message de l'utilisateur (déjà envoyé, avec le tableau) : « Voici les données d'un exercice (1200 mg par voie orale ; temps en min, concentration en ng/mL) : »
Tableau joint : 10 lignes, un sujet ; en-tête puis 5 premières lignes :

```
time (min),conc (ng/mL)
30,436.23
60,6.5416
90,0.098095
120,0.001471
180,3.3078e-07
```

Analyses déjà dans le projet : n°1 (NCA, AUC linéaire) ; n°2 (NCA, AUC lin-up/log-down)
Dernière demande de l'utilisateur : « Compare l'analyse 2 et l'analyse 1 pour l'AUC. »
`compare_pair` possibles : `not_applicable`, `1+2`, `2+1`

### ood-073

Tour 1 : première demande de la conversation.
Message de l'utilisateur : « Prise orale de 200 mg : Cmax, Tmax et AUC0-t. »
Tableau joint : 9 lignes, un sujet ; en-tête puis 5 premières lignes :

```
time (h),conc (ng/mL)
0.5,2044.7
1,3100.5
2,3768.2
3,3669.0
4,3352.2
```

Analyses déjà dans le projet : aucune
`compare_pair` possibles : `not_applicable`, `none_available`

### ood-074

Tour 1 : première demande de la conversation.
Message de l'utilisateur : « Bolus de 120 mg : Cmax et AUC0-inf. »
Tableau joint : 9 lignes, un sujet ; en-tête puis 5 premières lignes :

```
time (h),conc (mg/L)
0.25,5.2657
0.5,5.0835
1,4.7376
2,4.115
3,3.5741
```

Analyses déjà dans le projet : aucune
`compare_pair` possibles : `not_applicable`, `none_available`

## Rappel

Réponds maintenant par les 74 lignes JSON, et rien d'autre.
