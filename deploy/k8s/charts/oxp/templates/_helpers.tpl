{{/*
Expand the name of the chart.
*/}}
{{- define "oxp.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "oxp.fullname" -}}
{{- $global := get .Values "global" | default dict -}}
{{- $baseName := get $global "baseName" -}}
{{- if $baseName }}
{{- $baseName | trunc 63 | trimSuffix "-" }}
{{- else if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "oxp.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels.
*/}}
{{- define "oxp.labels" -}}
helm.sh/chart: {{ include "oxp.chart" . }}
{{ include "oxp.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels.
*/}}
{{- define "oxp.selectorLabels" -}}
app.kubernetes.io/name: {{ include "oxp.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{- define "oxp.secretName" -}}
{{- if .Values.secrets.llm.existingSecret -}}
{{- .Values.secrets.llm.existingSecret -}}
{{- else -}}
{{- default (printf "%s-llm-secret" (include "oxp.fullname" .)) .Values.secrets.llm.name -}}
{{- end -}}
{{- end }}

{{- define "oxp.workerSecretName" -}}
{{- $root := .root -}}
{{- $name := .name -}}
{{- printf "%s-worker-%s-secret" (include "oxp.fullname" $root) $name | trunc 63 | trimSuffix "-" -}}
{{- end }}

{{- define "oxp.workerDeploymentName" -}}
{{- $root := .root -}}
{{- $name := .name -}}
{{- printf "%s-worker-%s" (include "oxp.fullname" $root) $name | trunc 63 | trimSuffix "-" -}}
{{- end }}

{{- define "oxp.workerEnvConfigMapName" -}}
{{- printf "%s-worker-env-extra" (include "oxp.fullname" .) -}}
{{- end }}

{{- define "oxp.mceConfigMapName" -}}
{{- printf "%s-mce-config" (include "oxp.fullname" .) -}}
{{- end }}

{{- define "oxp.otelCollectorName" -}}
{{- printf "%s-otel-collector" (include "oxp.fullname" .) -}}
{{- end }}

{{- define "oxp.apiBaseUrl" -}}
{{- $apiValues := .Values.api | default dict -}}
{{- $externalConfig := get $apiValues "external" | default dict -}}
{{- $externalApi := get $externalConfig "baseUrl" | default "" -}}
{{- if $externalApi -}}
{{- $externalApi -}}
{{- else -}}
{{- $apiPort := int .Values.api.api.service.port -}}
{{- printf "http://%s-api.%s.svc.cluster.local:%d" (include "oxp.fullname" .) .Release.Namespace $apiPort -}}
{{- end -}}
{{- end -}}

{{- define "oxp.clickhouseName" -}}
{{- printf "%s-clickhouse" (include "oxp.fullname" .) -}}
{{- end }}

{{- define "oxp.clickhouseHost" -}}
{{- $clickhouseValues := .Values.clickhouse | default dict -}}
{{- $externalConfig := get $clickhouseValues "external" | default dict -}}
{{- $externalHost := get $externalConfig "host" | default "" -}}
{{- $global := .Values.global | default dict -}}
{{- $globalClickhouse := get $global "clickhouse" | default dict -}}
{{- $globalHost := get $globalClickhouse "host" | default "" -}}
{{- if $externalHost -}}
{{- $externalHost -}}
{{- else if $globalHost -}}
{{- $globalHost -}}
{{- else -}}
{{- printf "%s.%s.svc.cluster.local" (include "oxp.clickhouseName" .) .Release.Namespace -}}
{{- end -}}
{{- end }}

{{- define "oxp.clickhouseHttpPort" -}}
{{- $clickhouseValues := .Values.clickhouse | default dict -}}
{{- $externalConfig := get $clickhouseValues "external" | default dict -}}
{{- $externalPort := get $externalConfig "httpPort" | default "" -}}
{{- $global := .Values.global | default dict -}}
{{- $globalClickhouse := get $global "clickhouse" | default dict -}}
{{- $globalPort := get $globalClickhouse "port" | default (get $globalClickhouse "httpPort" | default "") -}}
{{- if $externalPort -}}
{{- $externalPort -}}
{{- else if $globalPort -}}
{{- $globalPort -}}
{{- else -}}
{{- .Values.clickhouse.service.ports.http -}}
{{- end -}}
{{- end }}

{{- define "oxp.clickhouseTcpPort" -}}
{{- $clickhouseValues := .Values.clickhouse | default dict -}}
{{- $externalConfig := get $clickhouseValues "external" | default dict -}}
{{- $externalPort := get $externalConfig "tcpPort" | default "" -}}
{{- $global := .Values.global | default dict -}}
{{- $globalClickhouse := get $global "clickhouse" | default dict -}}
{{- $globalPort := get $globalClickhouse "tcpPort" | default "" -}}
{{- if $externalPort -}}
{{- $externalPort -}}
{{- else if $globalPort -}}
{{- $globalPort -}}
{{- else -}}
{{- .Values.clickhouse.service.ports.tcp -}}
{{- end -}}
{{- end }}

{{- define "oxp.rabbitmqName" -}}
{{- printf "%s-rabbitmq" (include "oxp.fullname" .) -}}
{{- end }}

{{- define "oxp.rabbitmqHost" -}}
{{- $rabbitmqValues := .Values.rabbitmq | default dict -}}
{{- $externalConfig := get $rabbitmqValues "external" | default dict -}}
{{- $externalHost := get $externalConfig "host" | default "" -}}
{{- $global := .Values.global | default dict -}}
{{- $globalRabbitmq := get $global "rabbitmq" | default dict -}}
{{- $globalHost := get $globalRabbitmq "host" | default "" -}}
{{- if $externalHost -}}
{{- $externalHost -}}
{{- else if $globalHost -}}
{{- $globalHost -}}
{{- else -}}
{{- printf "%s.%s.svc.cluster.local" (include "oxp.rabbitmqName" .) .Release.Namespace -}}
{{- end -}}
{{- end }}

{{- define "oxp.rabbitmqPort" -}}
{{- $rabbitmqValues := .Values.rabbitmq | default dict -}}
{{- $externalConfig := get $rabbitmqValues "external" | default dict -}}
{{- $externalPort := get $externalConfig "port" | default "" -}}
{{- $global := .Values.global | default dict -}}
{{- $globalRabbitmq := get $global "rabbitmq" | default dict -}}
{{- $globalPort := get $globalRabbitmq "port" | default "" -}}
{{- if $externalPort -}}
{{- $externalPort -}}
{{- else if $globalPort -}}
{{- $globalPort -}}
{{- else -}}
{{- .Values.rabbitmq.service.ports.amqp -}}
{{- end -}}
{{- end }}

{{- define "oxp.neo4jName" -}}
{{- printf "%s-neo4j" (include "oxp.fullname" .) -}}
{{- end }}

{{- define "oxp.neo4jHost" -}}
{{- $neo4jValues := .Values.neo4j | default dict -}}
{{- $externalConfig := get $neo4jValues "external" | default dict -}}
{{- $externalHost := get $externalConfig "host" | default "" -}}
{{- $global := .Values.global | default dict -}}
{{- $globalNeo4j := get $global "neo4j" | default dict -}}
{{- $globalHost := get $globalNeo4j "host" | default "" -}}
{{- if $externalHost -}}
{{- $externalHost -}}
{{- else if $globalHost -}}
{{- $globalHost -}}
{{- else -}}
{{- printf "%s.%s.svc.cluster.local" (include "oxp.neo4jName" .) .Release.Namespace -}}
{{- end -}}
{{- end }}

{{- define "oxp.neo4jPort" -}}
{{- $neo4jValues := .Values.neo4j | default dict -}}
{{- $externalConfig := get $neo4jValues "external" | default dict -}}
{{- $externalPort := get $externalConfig "port" | default "" -}}
{{- $global := .Values.global | default dict -}}
{{- $globalNeo4j := get $global "neo4j" | default dict -}}
{{- $globalPort := get $globalNeo4j "port" | default "" -}}
{{- if $externalPort -}}
{{- $externalPort -}}
{{- else if $globalPort -}}
{{- $globalPort -}}
{{- else -}}
{{- $neo4jPort := 7687 -}}
{{- if and .Values.neo4j.services .Values.neo4j.services.default .Values.neo4j.services.default.ports .Values.neo4j.services.default.ports.bolt (hasKey .Values.neo4j.services.default.ports.bolt "port") -}}
{{- $neo4jPort = int .Values.neo4j.services.default.ports.bolt.port -}}
{{- end -}}
{{- $neo4jPort -}}
{{- end -}}
{{- end }}

{{- define "oxp.clickhouseSecretName" -}}
{{- default .Values.clickhouse.auth.secretName .Values.clickhouse.auth.existingSecret -}}
{{- end }}

{{- define "oxp.clickhouseUsersSecretName" -}}
{{- printf "%s-clickhouse-users" (include "oxp.fullname" .) -}}
{{- end }}

{{- define "oxp.clickhouseWorkerEnv" -}}
- name: CLICKHOUSE_HOST
  value: {{ include "oxp.clickhouseHost" . | quote }}
- name: CLICKHOUSE_PORT
  value: {{ include "oxp.clickhouseHttpPort" . | quote }}
- name: CLICKHOUSE_USERNAME
  valueFrom:
    secretKeyRef:
      name: {{ include "oxp.clickhouseSecretName" . }}
      key: {{ .Values.clickhouse.auth.usernameKey }}
- name: CLICKHOUSE_PASSWORD
  valueFrom:
    secretKeyRef:
      name: {{ include "oxp.clickhouseSecretName" . }}
      key: {{ .Values.clickhouse.auth.passwordKey }}
- name: CLICKHOUSE_DATABASE
  value: {{ .Values.clickhouse.database | quote }}
{{- end }}

{{- define "oxp.rabbitmqSecretName" -}}
{{- default .Values.rabbitmq.auth.secretName .Values.rabbitmq.auth.existingSecret -}}
{{- end }}

{{- define "oxp.rabbitmqUsernameKey" -}}
{{- default "username" .Values.rabbitmq.auth.usernameKey -}}
{{- end }}

{{- define "oxp.rabbitmqPasswordKey" -}}
{{- default "password" .Values.rabbitmq.auth.passwordKey -}}
{{- end }}

{{- define "oxp.rabbitmqWorkerEnv" -}}
- name: RABBITMQ_HOST
  value: {{ include "oxp.rabbitmqHost" . | quote }}
- name: RABBITMQ_PORT
  value: {{ include "oxp.rabbitmqPort" . | quote }}
- name: RABBITMQ_USER
  valueFrom:
    secretKeyRef:
      name: {{ include "oxp.rabbitmqSecretName" . }}
      key: {{ include "oxp.rabbitmqUsernameKey" . }}
- name: RABBITMQ_PASSWORD
  valueFrom:
    secretKeyRef:
      name: {{ include "oxp.rabbitmqSecretName" . }}
      key: {{ include "oxp.rabbitmqPasswordKey" . }}
- name: RABBITMQ_VHOST
  value: {{ default "/" .Values.rabbitmq.auth.vhost | quote }}
{{- end }}

{{- define "oxp.neo4jWorkerEnv" -}}
- name: NEO4J_HOST
  value: {{ include "oxp.neo4jHost" . | quote }}
- name: NEO4J_PORT
  value: {{ include "oxp.neo4jPort" . | quote }}
- name: NEO4J_URI
  value: {{ printf "bolt://%s:%s" (include "oxp.neo4jHost" .) (include "oxp.neo4jPort" .) | quote }}
- name: NEO4J_AUTH
  valueFrom:
    secretKeyRef:
      name: {{ include "oxp.neo4jAuthSecretName" . }}
      key: {{ .Values.neo4j.neo4j.authKey }}
- name: NEO4J_DB
  value: {{ default "neo4j" .Values.neo4j.database | quote }}
{{- end }}

{{- define "oxp.otelEndpoint" -}}
{{- $otelHttpPort := 4318 -}}
{{- if and .Values.otelCollector.ports (hasKey .Values.otelCollector.ports "otlp-http") -}}
{{- $otelHttpPort = int (index (index .Values.otelCollector.ports "otlp-http") "servicePort") -}}
{{- end -}}
{{- printf "http://%s.%s.svc.cluster.local:%d" (include "oxp.otelCollectorName" .) .Release.Namespace $otelHttpPort -}}
{{- end }}

{{- define "oxp.listOrStringEnvValue" -}}
{{- if kindIs "slice" . -}}
{{ join "," . }}
{{- else -}}
{{ . }}
{{- end -}}
{{- end }}

{{- define "oxp.neo4jSecretName" -}}
{{- if .Values.neo4j.neo4j.passwordFromSecret -}}
{{- .Values.neo4j.neo4j.passwordFromSecret -}}
{{- else -}}
{{- .Values.neo4j.neo4j.secretName -}}
{{- end -}}
{{- end }}

{{- define "oxp.neo4jAuthSecretName" -}}
{{- if .Values.neo4j.neo4j.passwordFromSecret -}}
{{- .Values.neo4j.neo4j.passwordFromSecret -}}
{{- else -}}
{{- printf "%s-auth" (include "oxp.neo4jName" .) -}}
{{- end -}}
{{- end }}

{{- define "oxp.neo4jUsernameKey" -}}
{{- .Values.neo4j.neo4j.usernameKey -}}
{{- end }}

{{- define "oxp.neo4jPasswordKey" -}}
{{- .Values.neo4j.neo4j.passwordKey -}}
{{- end }}

{{- define "oxp.clickhouseUsername" -}}
{{- .Values.clickhouse.auth.username -}}
{{- end }}

{{- define "oxp.clickhousePassword" -}}
{{- .Values.clickhouse.auth.password -}}
{{- end }}

{{- define "oxp.workerInitContainers.waitDependencies" -}}
{{- $root := .root -}}
{{- $includeClickhouse := default false .includeClickhouse -}}
{{- $waitConfig := $root.Values.workers.startupWait -}}
{{- if $waitConfig.enabled -}}
{{- $waitImage := $waitConfig.image -}}
{{- if $waitConfig.rabbitmq.enabled }}
- name: wait-for-rabbitmq
  image: {{ printf "%s:%s" $waitImage.repository $waitImage.tag | quote }}
  imagePullPolicy: {{ $waitImage.pullPolicy }}
  command:
    - sh
    - -c
    - |
      echo "Waiting for RabbitMQ at {{ include "oxp.rabbitmqHost" $root }}:{{ include "oxp.rabbitmqPort" $root }}"
      start=$(date +%s)
      until nc -z -w {{ $waitConfig.connectTimeoutSeconds }} {{ include "oxp.rabbitmqHost" $root }} {{ include "oxp.rabbitmqPort" $root }}; do
        now=$(date +%s)
        elapsed=$((now-start))
        if [ "$elapsed" -ge {{ $waitConfig.maxWaitSeconds }} ]; then
          echo "Timed out waiting for RabbitMQ after {{ $waitConfig.maxWaitSeconds }} seconds"
          exit 1
        fi
        echo "RabbitMQ not ready yet..."
        sleep {{ $waitConfig.retryIntervalSeconds }}
      done
{{- end }}
{{- if $waitConfig.neo4j.enabled }}
- name: wait-for-neo4j
  image: {{ printf "%s:%s" $waitImage.repository $waitImage.tag | quote }}
  imagePullPolicy: {{ $waitImage.pullPolicy }}
  command:
    - sh
    - -c
    - |
      echo "Waiting for Neo4j HTTP readiness at {{ include "oxp.neo4jHost" $root }}:7474"
      start=$(date +%s)
      until wget -q -T {{ $waitConfig.connectTimeoutSeconds }} -O /dev/null "http://{{ include "oxp.neo4jHost" $root }}:7474/"; do
        now=$(date +%s)
        elapsed=$((now-start))
        if [ "$elapsed" -ge {{ $waitConfig.maxWaitSeconds }} ]; then
          echo "Timed out waiting for Neo4j after {{ $waitConfig.maxWaitSeconds }} seconds"
          exit 1
        fi
        echo "Neo4j not ready yet..."
        sleep {{ $waitConfig.retryIntervalSeconds }}
      done
      echo "Neo4j is ready"
{{- end }}
{{- if and $includeClickhouse $waitConfig.clickhouse.enabled }}
- name: wait-for-clickhouse
  image: {{ printf "%s:%s" $waitImage.repository $waitImage.tag | quote }}
  imagePullPolicy: {{ $waitImage.pullPolicy }}
  command:
    - sh
    - -c
    - |
      echo "Waiting for ClickHouse at {{ include "oxp.clickhouseHost" $root }}:{{ include "oxp.clickhouseHttpPort" $root }}"
      start=$(date +%s)
      until nc -z -w {{ $waitConfig.connectTimeoutSeconds }} {{ include "oxp.clickhouseHost" $root }} {{ include "oxp.clickhouseHttpPort" $root }}; do
        now=$(date +%s)
        elapsed=$((now-start))
        if [ "$elapsed" -ge {{ $waitConfig.maxWaitSeconds }} ]; then
          echo "Timed out waiting for ClickHouse after {{ $waitConfig.maxWaitSeconds }} seconds"
          exit 1
        fi
        echo "ClickHouse not ready yet..."
        sleep {{ $waitConfig.retryIntervalSeconds }}
      done
{{- end }}
{{- end }}
{{- end }}

