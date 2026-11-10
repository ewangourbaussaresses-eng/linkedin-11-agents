# 🧠 LinkedIn 11 Agents — le système d'agents qui pilote votre LinkedIn

Onze agents spécialisés qui **analysent**, **rédigent**, **publient**, **supervisent** et
**apprennent** sur votre compte LinkedIn. Ils tournent en Python standard, se testent
hors ligne, et se pilotent de trois façons :

- 🖥️ **en ligne de commande** (`python -m linkedin_agents …`) ;
- 🌐 **depuis un navigateur** (mini-serveur web local, sans dépendance) ;
- 🤖 **depuis Claude.ai normal** — sans Claude Code : collez le fichier
  [`CLAUDE_PROJECT.md`](CLAUDE_PROJECT.md) dans un *Project* Claude, et Claude utilise
  les agents via leurs commandes.

Aucun compte LinkedIn n'est requis pour tester : le **mode simulation** (`--dry-run`)
fonctionne de bout en bout avec des données d'exemple.

---

## Les 11 agents

| # | Agent | Rôle | Commande |
|---|-------|------|----------|
| 1 | **Veille** (`watch`) | Collecte les tendances et sources d'inspiration (RSS, fichiers) et en tire des angles | `watch` |
| 2 | **Audience** (`audience`) | Analyse votre audience (export CSV) : personas, meilleurs créneaux, langues | `audience` |
| 3 | **Stratège** (`strategist`) | Construit le calendrier éditorial : piliers, formats, fréquence, trous | `strategist` |
| 4 | **Rédacteur** (`writer`) | Rédige les posts (hook, corps, CTA, hashtags) dans votre voix — **via Claude si une clé est configurée** | `writer` |
| 5 | **Éditeur** (`editor`) | Corrige, resserre, vérifie la lisibilité et les règles de style | `editor` |
| 6 | **Visuel** (`visual`) | Propose un brief visuel/carrousel + texte alternatif accessible | `visual` |
| 7 | **Programmateur** (`scheduler`) | Place les posts dans les créneaux optimaux et produit le calendrier | `scheduler` |
| 8 | **Publisher** (`publisher`) | Publie (API officielle ou simulation) et journalise chaque envoi | `publish` |
| 9 | **Engagement** (`engagement`) | Prépare réponses aux commentaires, suggestions de commentaires à faire — **via Claude si disponible** | `engagement` |
| 10 | **Superviseur** (`supervisor`) | Contrôle qualité : conformité, doublons, risque, cohérence de marque — bloque si besoin | `supervise` |
| 11 | **Analyste** (`analyst`) | Mesure les performances, en tire des apprentissages et met à jour la stratégie | `analyze` |

Chaque agent est un module autonome dans [`linkedin_agents/agents/`](linkedin_agents/agents/),
avec une fonction `run(ctx, payload)` testable et sans effet de bord caché.

---

## Démarrage rapide

```bash
git clone https://github.com/<votre-compte>/linkedin-11-agents.git
cd linkedin-11-agents

python -m venv .venv && source .venv/bin/activate   # Windows : .venv\Scripts\activate
pip install -r requirements.txt                      # uniquement pytest (tests)

# 1. Initialiser le profil de marque
python -m linkedin_agents init

# 2. Tout faire tourner en simulation (aucune publication réelle)
python -m linkedin_agents pipeline --dry-run

# 3. Interface web locale
python -m linkedin_agents serve        # http://localhost:8765
```

Résultats dans `workspace/` : `plan.json`, `drafts/`, `calendar.md`, `published/`,
`reports/`, `state.json`.

---

## Commandes

```bash
python -m linkedin_agents list                 # les 11 agents et leur statut
python -m linkedin_agents watch                # agent 1 : veille & angles
python -m linkedin_agents audience             # agent 2 : analyse d'audience
python -m linkedin_agents strategist           # agent 3 : calendrier éditorial
python -m linkedin_agents writer --topic "IA en PME"   # agent 4 : rédaction
python -m linkedin_agents editor --file drafts/x.md    # agent 5 : édition
python -m linkedin_agents visual --file drafts/x.md    # agent 6 : brief visuel
python -m linkedin_agents scheduler            # agent 7 : créneaux optimaux
python -m linkedin_agents supervise            # agent 10 : contrôle qualité
python -m linkedin_agents publish --dry-run    # agent 8 : publication
python -m linkedin_agents engagement           # agent 9 : réponses aux commentaires
python -m linkedin_agents analyze              # agent 11 : performances & apprentissages
python -m linkedin_agents pipeline --dry-run   # les 11 agents à la chaîne
python -m linkedin_agents serve                # interface web
```

Toutes les commandes acceptent `--help` et `--json` (sortie machine).

---

## Connecteur Claude (API Anthropic)

Les agents 4 (Rédacteur) et 9 (Engagement) **utilisent Claude quand une clé est
présente** ; sinon ils retombent automatiquement sur leurs gabarits locaux. Aucune clé
n'est jamais écrite dans le dépôt.

```bash
# 1. Récupérez une clé sur https://console.anthropic.com/
export ANTHROPIC_API_KEY="sk-ant-..."     # Windows PowerShell : $env:ANTHROPIC_API_KEY="sk-ant-..."

# 2. Vérifiez le branchement
python -m linkedin_agents llm              # fournisseur détecté + modèle
python -m linkedin_agents llm-test         # appel réel, réponse affichée

# 3. Lancez le pipeline : la rédaction passe par Claude
python -m linkedin_agents pipeline
```

Sortie typique :

```
PIPELINE LINKEDIN — … (simulation) — rédaction : Claude
 ✔ writer       12 brouillon(s) rédigé(s) — Claude
```

Variables reconnues :

| Variable | Rôle | Défaut |
|---|---|---|
| `ANTHROPIC_API_KEY` | active le connecteur Claude | — |
| `ANTHROPIC_MODEL` | modèle utilisé | `claude-sonnet-4-5` |
| `OPENAI_API_KEY` | repli si Claude absent | — |
| `OPENAI_MODEL` | modèle OpenAI | `gpt-4o-mini` |
| `LLM_PROVIDER` | `auto` \| `claude` \| `openai` \| `off` | `auto` |

Le fichier [`.env.example`](.env.example) liste toutes les variables. Copiez-le en `.env`
(ignoré par git) et chargez-le :

```bash
set -a; . ./.env; set +a          # bash / zsh
```

**Comportement en cas d'erreur** : si l'appel échoue (clé invalide, quota, réseau), le
brouillon est produit par le gabarit local et le pipeline continue — il ne casse jamais.

**Dans GitHub Actions** : ajoutez `ANTHROPIC_API_KEY` dans
*Settings → Secrets and variables → Actions*. Le workflow `pipeline.yml` l'injecte ;
sans secret, il tourne en gabarits locaux.

## Utilisation depuis Claude.ai (sans Claude Code)

1. Ouvrez Claude.ai → **Projects** → *New project* → **LinkedIn 11 Agents**.
2. Dans les *Project knowledge*, ajoutez :
   - [`CLAUDE_PROJECT.md`](CLAUDE_PROJECT.md) (les instructions du système),
   - votre `workspace/brand.json` et `workspace/plan.json`.
3. Discutez normalement : *« fais la veille de la semaine »*, *« écris 3 posts sur la
   cybersécurité pour PME »*, *« supervise et publie »*. Claude produit le contenu avec
   les agents et vous renvoie le JSON/Markdown à coller dans `workspace/`, ou à passer
   à la commande correspondante.

Le fichier `CLAUDE_PROJECT.md` contient les rôles, les formats d'entrée/sortie et les
garde-fous (pas de publication réelle sans validation).

---

## Publication réelle (LinkedIn API)

Par défaut : **simulation**. Pour publier réellement, il faut une application LinkedIn
Developer avec le scope `w_member_social`, puis :

```bash
export LINKEDIN_ACCESS_TOKEN="..."
export LINKEDIN_AUTHOR_URN="urn:li:person:xxxxxxxx"
python -m linkedin_agents publish            # sans --dry-run
```

Le publisher :

- respecte un **plafond quotidien** (`brand.json` → `limits.max_posts_per_day`) ;
- vérifie l'**approbation du superviseur** avant tout envoi ;
- journalise chaque publication dans `workspace/published/log.jsonl`.

---

## Interface web

```bash
python -m linkedin_agents serve      # http://localhost:8765
python -m linkedin_agents llm        # état du connecteur Claude
```

Tableau de bord : les 11 agents, un bouton « Exécuter » par agent, le pipeline complet en
un clic, et l'accès au calendrier et aux rapports. Zéro dépendance (serveur stdlib).

## Tests

```bash
python -m pytest -q     # 46 tests, aucun accès réseau (LLM simulé)
```

---

## Structure

```
linkedin-11-agents/
├── linkedin_agents/
│   ├── __main__.py          # CLI
│   ├── context.py           # profil de marque, état, chemins
│   ├── orchestrator.py      # pipeline des 11 agents
│   ├── llm.py               # connecteur Claude / OpenAI (repli gabarits)
│   ├── linkedin_api.py      # client API (ou simulation)
│   ├── web.py               # interface web locale (stdlib)
│   └── agents/              # 1 module par agent
├── data/                    # exemples (audience, sources, commentaires)
├── workspace/               # sorties (ignoré par git)
├── tests/
├── .github/workflows/       # CI
├── CLAUDE_PROJECT.md        # instructions pour un Project Claude
└── README.md
```

---

## Licence

MIT — voir [LICENSE](LICENSE).
