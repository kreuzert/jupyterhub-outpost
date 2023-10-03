{{/*
Expand the name of the chart.
*/}}
{{- define "jupyterhub-outpost.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
We truncate at 63 chars because some Kubernetes name fields are limited to this (by the DNS naming spec).
If release name contains chart name it will be used as a full name.
*/}}
{{- define "jupyterhub-outpost.fullname" -}}
{{- if .Values.fullnameOverride }}
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
{{- define "jupyterhub-outpost.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "jupyterhub-outpost.labels" -}}
helm.sh/chart: {{ include "jupyterhub-outpost.chart" . }}
{{ include "jupyterhub-outpost.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "jupyterhub-outpost.selectorLabels" -}}
app.kubernetes.io/name: {{ include "jupyterhub-outpost.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Create the name of the service account to use
*/}}
{{- define "jupyterhub-outpost.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "jupyterhub-outpost.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}


{{- /* Ingress */}}
{{- define "jupyterhub-outpost.ingress.fullname" -}}
    {{- if (include "jupyterhub-outpost.fullname" .) }}
        {{- include "jupyterhub-outpost.fullname" . }}
    {{- else -}}
        jupyterhub
    {{- end }}
{{- end }}
