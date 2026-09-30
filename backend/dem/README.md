# Advanced Insights

## Overview

The `dem` package is a core component of the `mas-model` project, offering a powerful suite of utilities designed to extract advanced insights from your data. It provides essential functionalities for:

*   **Anomaly Detection**: Identifying unusual patterns or outliers in datasets.
*   **Consistency Checking**: Ensuring data integrity and uniformity.
*   **Embeddings**: Transforming complex data (like text) into numerical representations for machine learning tasks.
*   **Grouping**: Clustering similar data points based on various criteria, including semantic meaning.
*   **Lightweight LLM Adapters**: Facilitating integration with Large Language Models for enhanced capabilities.

This package serves as a foundational toolkit for data analysis and intelligent system development within the `mas-model` ecosystem.

### Example Usage

To begin using the `dem` package, import the desired detectors and helper functions directly from `mas_model.dem`. The examples below illustrate common use cases; for detailed information on exact signatures and expected input formats, please refer to the respective docstrings.

Here are some practical examples demonstrating the core functionalities of the `dem` package:

#### 1. Embedding Text

Transform a single sentence into a dense vector representation using a pre-trained Sentence Transformer model. This is useful for tasks like similarity search, clustering, or input to other machine learning models.

```python
from mas_model.dem.embedding import SentenceTransformerEmbedder

# Initialize the embedder with a specified model ID (SBERT in this case)
embedder = SentenceTransformerEmbedder(model_id="all-mpnet-base-v2")

# Encode a single sentence
sentence = "Hello, world!"
embedding = embedder.encode([sentence])

print(f"Original sentence: '{sentence}'")
print(f"Embedding vector shape: {embedding.shape}")
print(f"First 5 elements of the embedding: {embedding[0, :5]}...")
```

#### 2. Anomaly Detection

Identify anomalous values within a list of numerical metrics. The `MetricAnomalyDetector` helps pinpoint data points that deviate significantly from the norm.

```python
from mas_model.dem.anomaly import MetricAnomalyDetector

# Initialize the anomaly detector
md = MetricAnomalyDetector()

# Example metric values, including some potential outliers
metric_values = [1, 1.1, 0.9, 1.11, 1, 1.1, 0.9, 1.11, 1.11, 1, 1.1, 0.9, 1.11, 10, 11]

# Detect outliers
result = md.detect_outliers(metric_values)

print(f"Input metric values: {metric_values}")
print(f"Detected {len(result.outliers_values)} anomalies: {result.outliers_values}")
print(f"Indices of anomalies: {result.outliers_indices}")
```

#### 3. Metric Consistency

Measure the consistency of a set of metric values. This can be crucial for monitoring system health or data quality over time.

```python
from mas_model.dem.consistency import MetricConsistency

# Initialize the consistency calculator
mc = MetricConsistency()

# Example metric values
metric_values = [1, 1.1, 0.9, 1.11, 1, 1.1, 0.9, 1.11, 1.11, 1, 1.1, 0.9, 1.11, 10, 11]

# Calculate consistency
result = mc.calculate_consistency(metric_values)

print(f"Input metric values: {metric_values}")
print(f"Consistency result: {result}")
```

#### 4. Semantic Grouping

Group semantically equivalent queries or sentences together using embeddings. This is particularly useful for tasks like deduplication, clustering user queries, or organizing large text datasets.

```python
import json
from dem.embedding import GoogleEmbedder
from dem.grouping import SemanticGrouper

sentences = [
    "The cat chased the mouse.",
    "The mouse was chased by the cat.",
    "She is an excellent painter.",
    "She paints exceptionally well.",
]

# Encode the sentences into embeddings
embedder = GoogleEmbedder(model_id="gemini-embedding-001")
embeddings = embedder.encode(sentences)

# Compute semantic groups
sg = SemanticGrouper()
result = sg.cluster_embeddings_with_radius(embeddings)

print("Input sentences:")
for i, s in enumerate(sentences):
    print(f"  [{i}] {s}")

print("\nGrouping results (clusters of semantically similar sentences):")
print(json.dumps(result, indent=2))
```
 
