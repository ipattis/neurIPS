# Enrichment faithfulness audit

Judge: `us.anthropic.claude-sonnet-4-6`, 600 papers sampled across years.

| Field | Faithful | Minor issue | Unsupported |
|---|---|---|---|
| summary | 97.7% | 2.3% | 0.0% |
| problem | 82.3% | 17.7% | 0.0% |
| method | 93.0% | 6.8% | 0.2% |
| eli5 | 95.8% | 4.2% | 0.0% |
| applications | 73.2% | 26.7% | 0.2% |

**Papers with at least one unsupported field: 2 / 600 (0.3%)**

## Examples of flagged issues

- *Distribution Guidance Network for Weakly Supervised Point Cloud Semantic Segmentation* (2024): The problem description says 'sparse annotations' but the abstract uses 'weak supervision' / 'inadequate supervision signals' — sparse annotations is one interpretation but the abstract does not specifically frame it that way, making this a slight overstatement. (minor issue); The applications field claims the work 'directly advances 3D scene understanding from LiDAR or depth-sensor point clouds' — neither LiDAR nor depth sensors are mentioned anywhere in the abstract, making this an unsupported specific claim.
- *Reliable Decision‑Making via Calibration‑Oriented Retrieval‑Augmented Generation* (2025): The problem description adds a specific definition of calibration ('ensuring that the model's confidence aligns with actual correctness') that the abstract does not state; the abstract only says prior RAG methods do not 'specifically aim to ensure that the human user's decisions are well-calibrated', making the elaboration a minor addition beyond what is stated.; The method description claims CalibRAG 'selects documents to ensure that the resulting LLM outputs have confidence levels aligned with their actual correctness probability' and 'explicitly optimize for calibration rather than just relevance'. The abstract describes CalibRAG only as a 'novel retrieval method...which ensures that decisions informed by RAG are well-calibrated' but gives no detail about how documents are selected or that confidence-probability alignment is the optimization target. This is a specific mechanistic claim not supported by the abstract.
