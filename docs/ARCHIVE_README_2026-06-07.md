# CSI Bid Intelligence: Agentic Competitive Analysis System

**Status**: ✅ **PHASE 1 COMPLETE** | ⏳ **Phase 2-3 In Progress**

Multi-agent system for analyzing construction bid data, identifying project types, and determining optimal bidding strategy through competitive intelligence.

## 🔄 Overall System Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                    PROPOSED AGENTIC WORKFLOW                    │
└─────────────────────────────────────────────────────────────────┘

INPUT                PROCESSING              OUTPUT              FINAL
(User                (Agents Extract &      (Analyze &          (Recommendation)
Provides)            Process)               Score)

   ↓                    ↓                      ↓                    ↓
┌──────────┐    ┌──────────────┐    ┌─────────────────┐    ┌──────────────┐
│ Upload   │    │ Plan Reader  │    │ Competitor      │    │ Determine    │
│ New      │───→│ Agent        │───→│ Scoring Engine  │───→│ CSI Should   │
│ Project  │    │              │    │ & Intelligence  │    │ Bid + Advice │
│ Proposal │    │ • Scan text  │    │ Sub-agents      │    │ on Strategy  │
│ to CSI   │    │ • Extract    │    │                 │    │              │
│ bid list │    │   key info   │    │ • Job type      │    └──────────────┘
└──────────┘    │ • Material   │    │   similarity    │
                │   quantities │    │ • Pit distance  │
                │ • Parsing    │    │ • Recent        │
                │              │    │   capacity      │
                └──────────────┘    │ • LLM           │
                                    │   Explanation   │
                                    └─────────────────┘
```

**Phases**:
- **Phase 1** ✅ (COMPLETE): Data cleaning + project-type clustering
- **Phase 2** (TBD): Plan Reader Agent + Competitor Scoring Engine  
- **Phase 3** (TBD): Bidding Strategy Engine + Chatbot Interface

---

## 📁 Project Structure (Current & Planned)

### **Current Structure** (Phase 1 Complete)

```
csi-bid-intelligence/
├── data/                      # Data at various stages
│   ├── raw/                   # Original 2024/2025 source files
│   ├── processed/             # Cleaned combined data (CSI_data_combined.csv)
│   ├── cleaning_review/       # QA artifacts from data cleaning
│   └── README.md
│
├── clustering/                # ✅ PHASE 1: Project-type clustering (COMPLETE)
│   ├── scripts/               # Python analysis code
│   ├── results/               # Clustering outputs (CSVs)
│   ├── visualizations/        # All plots & charts
│   └── README.md
│
├── docs/                      # Reference documentation
│   ├── CLUSTERING_PLAN.md     # Complete methodology + results (PRIMARY)
│   ├── CHANGELOG.md           # Data cleaning lineage
│   ├── PCA_INTERPRETATION_GUIDE.txt
│   └── README.md
│
├── archived/                  # Historical/completed scripts
│   ├── clean_data.py
│   └── pca_component_analysis.py
│
└── README.md                  # This file
```

### **Planned Structure** (Phase 2 & 3)

```
csi-bid-intelligence/
├── data/
├── clustering/               # ✅ Phase 1 (existing)
├── docs/
├── archived/
│
├── agents/                   # ⏳ PHASE 2 & 3: Multi-agent system
│   ├── plan_reader/          # Extract project proposals
│   │   ├── scripts/
│   │   ├── models/           # Pre-trained models/embeddings
│   │   ├── results/
│   │   └── README.md
│   │
│   ├── competitor_scoring/   # Analyze & rank competitors
│   │   ├── scripts/
│   │   ├── results/
│   │   └── README.md
│   │
│   └── strategy/             # Bidding recommendations
│       ├── scripts/
│       ├── results/
│       └── README.md
│
├── interface/                # ⏳ PHASE 3: User-facing systems
│   ├── chatbot/              # Q&A interface
│   │   ├── scripts/
│   │   ├── prompts/          # LLM prompt templates
│   │   └── README.md
│   │
│   └── web/                  # (Optional) Web dashboard
│
└── README.md
```

See `data/README.md`, `clustering/README.md`, and `docs/README.md` for details on current folders.  
Phase 2 & 3 folder structure TBD based on agent implementation approach.

---

## 🎯 System Components & Phases

### **PHASE 1** ✅ **COMPLETE: Project-Type Clustering**

**Goal**: Identify what types of projects CSI bids on  
**Status**: ✅ Production-ready

**What it does**:
- Analyzed 1,661 historical projects (2024-2025)
- Discovered **5 distinct project types** using K-Medoids + K-Modes hybrid clustering
- Mapped 7 material variables (asphalt, grading, base, shoulders, milling, crushing, stockpile) + infrastructure type (BOX culverts)

**Key Results**:
- **Cluster 0** (72%): Routine/Maintenance projects
- **Cluster 1** (22%): Medium Asphalt Overlay
- **Cluster 2** (5%): Large Projects
- **Cluster 3** (1%): Extreme Structural (with culverts)
- **Cluster 4** (1%): **Extreme Grading** ← NEW discovery (1.7M cubic yards avg)
- **Silhouette Score**: 0.5700 (exceeds 0.4 target) ✅

**Implementation**:
- Location: `clustering/` folder
- Scripts: `clustering_analysis.py`, `visualize_tuning_decisions.py`, `interpret_pca_results.py`
- Output: `clustering/results/CSI_data_combined_with_clusters.csv`

---

### **PHASE 2** ⏳ **TODO: Plan Reader Agent + Competitor Intelligence**

**Goal**: For a new project proposal, extract info & identify likely competitors  
**Status**: Design phase (see notes below)

**Components**:

#### **2a. Plan Reader Agent** (TBD)
*Extracts structured data from project proposals*

**Input**: New project proposal PDF/document  
**Processing**:
- [ ] Extract project metadata (location, scope, materials)
- [ ] Parse material quantities & types
- [ ] Identify infrastructure requirements (culverts, etc.)
- [ ] Assign to a project-type cluster (from Phase 1)

**Output**: Structured project data (project_csv with material breakdown)

**Questions to answer**:
- Use Claude PDF feature or pdftotext for extraction?
- Single-pass or multi-pass validation?
- How to handle ambiguous material specifications?
- Link to Phase 1 clusters: K-nearest neighbors or scoring?

---

#### **2b. Competitor Scoring Engine** (TBD)
*Determines which competitors likely bid on this project type*

**Input**: Project cluster assignment (from Plan Reader Agent)  
**Processing**:
- [ ] **Job Type Similarity**: Which competitors bid most on similar projects?
- [ ] **Geographic Proximity**: Calculate pit/facility distance to project
- [ ] **Recent Capacity**: Did they bid frequently in last 12 months?
- [ ] **Market Concentration**: Score based on bid frequency & success

**Output**: Ranked competitor list with confidence scores

**Scoring Formula** (TBD):
```
Competitor Score = (similarity_weight × job_similarity) 
                 + (distance_weight × pit_proximity)
                 + (capacity_weight × recent_capacity)
```

**Questions to answer**:
- How to weight the three signals?
- How fresh should capacity data be (3mo, 6mo, 12mo)?
- How to handle new competitors not in historical data?
- Confidence intervals or point scores?

---

### **PHASE 3** ⏳ **TODO: LLM Explanation + Bidding Strategy**

**Goal**: Recommend bidding strategy with reasoning  
**Status**: Placeholder (see notes below)

**Components**:

#### **3a. LLM Explanation Layer** (TBD)
*Converts scores into natural language reasoning*

**Input**: Ranked competitor list + project details  
**Processing**:
- [ ] Generate explanations for each competitor score
- [ ] Identify market dynamics (concentrated vs fragmented)
- [ ] Surface risks & opportunities

**Output**: Natural language summary per competitor

**Example Output** (TBD):
> "ABC Construction ranks #1 (score: 0.87) because they bid on 5 similar grading projects in 2025 and their pit is 12 miles away. They appear to be our primary competition."

**Questions to answer**:
- How detailed should explanations be?
- Include confidence/uncertainty language?
- How to surface non-obvious patterns?

---

#### **3b. Bidding Strategy Engine** (TBD)
*Recommends CSI bidding approach*

**Input**: Project type + competitor analysis + historical CSI bids  
**Processing**:
- [ ] Calculate CSI win rate for this cluster
- [ ] Estimate material-to-bid ratio
- [ ] Compare CSI capacity vs demand
- [ ] Identify market gaps (under-served clusters)
- [ ] Recommend bid/no-bid decision

**Output**: Recommendation + confidence score

**Example Recommendation** (TBD):
> "**RECOMMEND BID** (75% confidence). This is a Cluster 1 (Medium Asphalt Overlay) where CSI has a 45% historical win rate. Only 2 competitors detected. Material estimate: $XXX. Estimated bid range: $X-$X."

**Questions to answer**:
- How to estimate expected profit margin?
- How to factor in CSI capacity constraints?
- What metrics determine "under-served"?
- How to handle new project types?

---

#### **3c. Chatbot Interface** (TBD)
*User-facing Q&A system*

**Input**: User questions about projects & competitors  
**Capabilities** (TBD):
- [ ] "Who are the likely competitors for this project?"
- [ ] "What is this project about?" (Q&A from embeddings)
- [ ] "What did CSI bid on similar projects?"
- [ ] "Which competitors are most active?"

**Architecture** (TBD):
- Vector DB (ChromaDB) for semantic search of project descriptions?
- Claude API for conversational Q&A?
- Rule-based routing or LLM-based?

**Questions to answer**:
- Web interface, Slack bot, or CLI tool?
- What's the minimum MVP?
- How to handle out-of-scope questions?

---

## 🚀 Quick Start

### View the Results
1. **Read the plan**: `docs/CLUSTERING_PLAN.md` (5 min for summary, 30 min for full details)
2. **See the clusters**: `clustering/visualizations/` (PNG plots)
3. **Check the data**: `clustering/results/CSI_data_combined_with_clusters.csv` (excel-friendly CSV)

### Run the Clustering
```bash
cd clustering/scripts/
python clustering_analysis.py          # Main clustering (5 min)
python visualize_tuning_decisions.py   # Parameter tuning viz (3 min)
python interpret_pca_results.py        # PCA interpretation (3 min)
```

### Understand the Methodology
- `docs/CLUSTERING_PLAN.md` - Sections 1-5 for approach
- `docs/PCA_INTERPRETATION_GUIDE.txt` - What each component means
- `clustering/visualizations/pca_component_loadings.png` - Visual guide

---

## 📊 Key Files by Purpose

| Goal | File/Folder |
|------|-------------|
| **View results** | `clustering/visualizations/` |
| **Access clustered data** | `clustering/results/CSI_data_combined_with_clusters.csv` |
| **Understand methodology** | `docs/CLUSTERING_PLAN.md` |
| **Check cluster profiles** | `clustering/results/cluster_statistics.csv` |
| **Run analysis** | `clustering/scripts/clustering_analysis.py` |
| **Learn about data** | `data/processed/CSI_data_combined.csv` |
| **Check data quality** | `data/cleaning_review/` |

---

## 📈 Clustering Results Summary

```
Input:   1,661 projects (2024-2025 historical data)
         7 material variables + 1 infrastructure variable
         
Process: StandardScaler → PCA (4 components, 77.2% variance)
         K-Medoids + K-Modes hybrid (gamma=0.1, k=5)
         
Output:  5 project types with silhouette score 0.5700
         
Key Finding: Gamma=0.1 means materials (not infrastructure) 
             drive project type differences
             
Surprise: Cluster 4 (extreme grading, 1.7M cubic yards avg)
          was not in original plan but emerged from data
```

See `docs/CLUSTERING_PLAN.md` Section 11 for full details.

---

## 🔄 Data Lineage

```
CSI_data_2024.csv (raw)  ─┐
                          ├→ Combined & Cleaned
CSI_data_2025.csv (raw)  ─┤
                          │
                          └→ CSI_data_combined.csv (processed)
                             ↓
                             Clustering Analysis
                             ↓
                             CSI_data_combined_with_clusters.csv (RESULT)
```

See `docs/CHANGELOG.md` for cleaning details.

---

## 💻 Technical Details

- **Language**: Python 3.7+
- **Key Libraries**: scikit-learn, scikit-learn-extra, scipy, pandas, matplotlib
- **Algorithm**: K-Medoids + K-Modes hybrid with gamma-weighted Euclidean + Hamming distance
- **Data Size**: 1,661 projects × 67 columns
- **Reproducibility**: All scripts use `random_state=42` for consistent results
- **Computation**: ~10 seconds total for full pipeline

---

## 📚 Documentation

| Document | Purpose | Read Time |
|----------|---------|-----------|
| `docs/CLUSTERING_PLAN.md` | Complete methodology + results | 30 min |
| `docs/CHANGELOG.md` | Data cleaning decisions | 10 min |
| `docs/PCA_INTERPRETATION_GUIDE.txt` | What PCA components mean | 5 min |
| `clustering/README.md` | How to run clustering | 5 min |
| `data/README.md` | Data file guide | 5 min |

**Start with**: `docs/CLUSTERING_PLAN.md` Executive Summary (top of file)

---

## ✅ Success Criteria (All Met)

- ✅ Interpretable clusters (5 distinct project types)
- ✅ Balanced clusters (no single >90%)
- ✅ Silhouette score > 0.4 (achieved 0.5700)
- ✅ Stable/reproducible (random_state=42)
- ✅ Documented methodology
- ✅ Code is reusable & maintainable

---

## 🔮 Development Roadmap

### **Phase 1** ✅ COMPLETE
- [x] Data cleaning & standardization
- [x] Project-type clustering (5 types identified)
- [x] Cluster profiling & interpretation
- [x] Full documentation

**Timeline**: 2026-06-06 to 2026-06-07  
**Output**: `clustering/results/CSI_data_combined_with_clusters.csv`

---

### **Phase 2** ⏳ NEXT (Estimated: 2-3 weeks)

**Plan Reader Agent**:
- [ ] Design PDF/text extraction pipeline
- [ ] Implement material quantity parser
- [ ] Build cluster assignment logic
- [ ] Validate on sample projects

**Competitor Scoring Engine**:
- [ ] Define scoring weights
- [ ] Implement similarity metrics
- [ ] Calculate geographic distances (geopy)
- [ ] Build bid frequency analyzer
- [ ] Output competitor rankings

**Testing & Validation**:
- [ ] Test on 20 new projects
- [ ] Validate competitor predictions vs. actual bids
- [ ] Refine weights based on test results

**Planned Folder**: `agents/plan_reader/` and `agents/competitor_scoring/`

---

### **Phase 3** ⏳ FUTURE (Estimated: 3-4 weeks after Phase 2)

**LLM Explanation Layer**:
- [ ] Design prompt templates
- [ ] Test with Claude API
- [ ] Generate natural language explanations

**Bidding Strategy Engine**:
- [ ] Calculate CSI win rates per cluster
- [ ] Implement bid/no-bid decision logic
- [ ] Build confidence scoring

**Chatbot Interface**:
- [ ] Choose platform (CLI, web, Slack)
- [ ] Build Q&A engine
- [ ] Integrate with vector DB

**Planned Folder**: `agents/strategy/` and `interface/chatbot/`

---

### **Continuous Improvement** (Ongoing)
- Monthly: Retrain clustering with new bid data
- Quarterly: Review & adjust competitor scoring weights
- As-needed: Update strategy recommendations based on win/loss analysis

---

## ❓ Design Questions & Decision Framework

### **For Phase 2 (Plan Reader Agent)**
- [ ] **Data Extraction**: Claude PDF feature vs. pdftotext + regex parsing?
- [ ] **Validation**: Single-pass or multi-pass extraction with verification?
- [ ] **Cluster Assignment**: K-nearest neighbors or probabilistic scoring?
- [ ] **Confidence Scoring**: How confident should we be in cluster assignments?
- [ ] **Material Handling**: How to normalize different measurement units/conventions?

### **For Phase 2 (Competitor Scoring)**
- [ ] **Scoring Weights**: How much weight for job_type vs. distance vs. capacity? (suggest: equal at 1/3 each to start)
- [ ] **Time Windows**: How fresh should capacity data be? (suggest: rolling 12-month window)
- [ ] **New Competitors**: How to handle competitors not in historical data? (suggest: baseline score + low confidence)
- [ ] **Geographic Distance**: Pit locations available? Or estimate from bid locations? (needs: pit_locations.csv)
- [ ] **Bid Frequency**: Raw count vs. normalized by competitor size? (suggest: raw count to start, normalize later)

### **For Phase 3 (LLM Explanation Layer)**
- [ ] **Explanation Style**: Formal technical vs. conversational business language?
- [ ] **Uncertainty**: Always express confidence/caveats? or just top predictions?
- [ ] **Novel Insights**: Should it identify non-obvious patterns or just explain scores?
- [ ] **Model**: Claude Opus (most capable) vs. Sonnet (faster, cheaper)?

### **For Phase 3 (Bidding Strategy Engine)**
- [ ] **Win Rate Data**: Do we have historical CSI win/loss data? (needed for per-cluster rates)
- [ ] **Cost Model**: Material costs available? Or estimate from historical bids?
- [ ] **Capacity Constraints**: Does CSI have crew/equipment capacity limits? (needed for volume decisions)
- [ ] **Market Definition**: How to define "market gap"? (suggest: clusters where CSI has < 20% historical win rate)
- [ ] **Bid/No-Bid Decision**: Hard threshold or probabilistic recommendation? (suggest: recommend if expected profit > X% threshold)

### **For Phase 3 (Chatbot)**
- [ ] **Platform**: CLI tool, web app, Slack bot, or all three?
- [ ] **Q&A Backend**: Vector embeddings (ChromaDB) or rule-based routing?
- [ ] **Scope**: What questions should it answer vs. decline?
- [ ] **Data**: What historical context does it need access to?
- [ ] **Freshness**: How often to update embeddings/indexes?

---

## 📊 Success Metrics (To Define)

### **Phase 2 Success Criteria** (TBD)
- [ ] Plan Reader extracts materials within 10% accuracy vs. manual review
- [ ] Competitor predictions match actual bids for 70%+ of new projects
- [ ] Scoring engine runs in < 5 seconds per project
- [ ] Team consensus on scoring weights

### **Phase 3 Success Criteria** (TBD)
- [ ] Bidding recommendations improve CSI win rate by 5-10%
- [ ] False positive rate (recommend bid when shouldn't) < 10%
- [ ] Strategy engine identifies profitable opportunities CSI had missed
- [ ] Chatbot answers 90%+ of user questions correctly

---

## 👤 Contact & Governance

**Project**: CSI Bid Intelligence System  
**Phase 1 Complete**: 2026-06-07  
**Author**: Quinten  
**Status**: ✅ Phase 1 (Clustering) Complete | ⏳ Phase 2-3 In Design  

**Decision Makers** (TBD):
- Clustering approach: Quinten ✅
- Phase 2 agent design: _[TBD: who decides plan reader vs. competitor scoring architecture?]_
- Phase 3 strategy logic: _[TBD: who validates bidding strategy rules?]_
- Phase 3 chatbot UX: _[TBD: who is the end user and what's their workflow?]_

**Review Checkpoints**:
- [ ] Phase 2 design review (before coding)
- [ ] Phase 2 validation (test on 20 new projects)
- [ ] Phase 3 design review (before coding)
- [ ] Phase 3 pilot (test with CSI team)

---

## 📝 Notes & Conventions

- **All CSV files**: UTF-8 encoding, comma delimiters
- **All scripts**: Use relative paths, execute from their respective directories
- **Data files**: Read-only after generation (checked into git)
- **Version control**: Full git history preserved for audit trail
- **Reproducibility**: All Phase 1 scripts use `random_state=42`
- **Documentation**: Each phase should have a README in its folder + design decisions doc
