{{- define "kafka-metrics-exporter.name" -}}
kafka-metrics-exporter
{{- end }}

{{- define "kafka-metrics-exporter.chart" -}}
{{ .Chart.Name }}-{{ .Chart.Version }}
{{- end }}
