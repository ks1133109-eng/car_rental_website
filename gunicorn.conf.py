import os

# 🔥 Reduce workers (most important fix)
workers = 2

# 🔥 Use threads instead of gevent (better for your app)
worker_class = "gthread"
threads = 2

# Reduce pressure
worker_connections = 50

timeout = 120
keepalive = 5
graceful_timeout = 30

bind = f"0.0.0.0:{os.environ.get('PORT', '5000')}"

accesslog = '-'
errorlog = '-'
loglevel = 'info'

preload_app = True

max_requests = 500
max_requests_jitter = 50
