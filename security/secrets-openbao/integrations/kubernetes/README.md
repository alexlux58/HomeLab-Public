# Kubernetes integration (deferred)

No k3s/Kubernetes cluster currently exists, so nothing is deployed. A future
phase must use Kubernetes auth, one policy per namespace/service account,
NetworkPolicy, TLS, short tokens, explicit reviewer/issuer configuration, and a
tested Agent Injector/CSI/External Secrets choice. A cluster-wide secret reader
is prohibited.
