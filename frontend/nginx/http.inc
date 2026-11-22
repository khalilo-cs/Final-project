# Shared by nginx.conf (HTTP) and nginx-tls.conf (HTTPS).
limit_req_zone $binary_remote_addr zone=api:10m rate=20r/s;
limit_req_zone $binary_remote_addr zone=login:10m rate=10r/m;
limit_req_status 429;
# WebSocket upgrade for the live viva (/svc/viva/ws/viva/{id}).
map $http_upgrade $connection_upgrade { default upgrade; "" close; }
