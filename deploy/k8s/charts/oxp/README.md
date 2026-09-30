# OXP Helm Chart

This document describes how to deploy the `oxp` umbrella chart.

## Quick start

Build the chart dependencies locally before installing:

```bash
helm dependency build charts/oxp
helm upgrade -i -n oxp oxp charts/oxp --create-namespace
```

By default, the chart enables an internal OXP gateway service (`oxp-gateway`) that routes:

- `/` to UI
- `/gql`, `/api/v1`, and `/api/v1alpha` to API

This enables a single local port-forward workflow:

```bash
kubectl -n oxp port-forward svc/oxp-gateway 8080:8080
```

Then open `http://localhost:8080`.

For ingress-based environments, keep this gateway pattern and expose only the gateway
via ingress to preserve same-origin browser calls.

## Deployment details for OXP with Helm

### 1. Prerequisites

- A Kubernetes cluster (for example Kind).
- Helm 3.x.
- `kubectl` configured for your target cluster.

### 2. Create Namespace

```bash
kubectl create namespace oxp
```

### 3. Create Image Pull Secret (GHCR)

Create a Docker registry secret in the same namespace where you install the chart.

```bash
kubectl -n oxp create secret docker-registry ghcr-pull-secret \
  --docker-server=ghcr.io \
  --docker-username=<github-username> \
  --docker-password=<github-token> \
  --docker-email=<email>
```

Use a GitHub token with at least `read:packages` scope.

### 4. Configure Global Pull Secret

In `values.yaml`, set:

```yaml
global:
  imagePullSecrets:
    - name: ghcr-pull-secret
```

This is used by workers and also by API/UI by default.

### 5. Existing Secrets Pattern (Summary)

Most components support the same pattern:

- If an `existingSecret`-style field is empty, the chart creates a secret from inline values.
- If that field is set, the chart reads credentials from your pre-created Kubernetes Secret.

This pattern is used across several components, including LLM, ClickHouse, RabbitMQ, and Neo4j.

RabbitMQ is the exception where the split configuration path needs a real password. For local testing, the chart ships with a non-empty placeholder, but for any shared or production deployment you should set `rabbitmq.auth.existingSecret` and store credentials in Kubernetes instead of relying on inline values.

General example:

```bash
kubectl -n oxp create secret generic <your-secret-name> \
  --from-literal=<username-key>=<username> \
  --from-literal=<password-key>=<password>
```

Then point the component values to that secret name/key mapping.

For Neo4j specifically, the existing auth secret commonly uses one key with `username/password` format:

```bash
kubectl -n oxp create secret generic oxp-neo4j-secret \
  --from-literal=NEO4J_AUTH='neo4j/<password>'
```

Important for local/simple installs:

- Neo4j data is persistent. If a prior install already initialized a different password,
  reinstalling the chart may keep the old DB password via existing PVC/secret state.
- If workers fail with `Neo.ClientError.Security.Unauthorized`, either:
  1) provide an explicit existing auth secret that matches the running Neo4j DB password, or
  2) reset the local Neo4j data/secret before reinstalling.

### 6. Install / Upgrade

From a local checkout of this repository:

```bash
helm dependency build charts/oxp
helm upgrade -i -n oxp oxp charts/oxp
```

### 7. Verify

```bash
kubectl get pods -n oxp
kubectl get svc -n oxp
```
