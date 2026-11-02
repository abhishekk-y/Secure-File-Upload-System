import os
from waitress import serve
from app import create_app, MAX_FILE, MAX_REQUEST_OVERHEAD

if __name__ == '__main__':
    port = int(os.getenv('PORT', '5000'))
    host = os.getenv('HOST', '127.0.0.1')
    print(f'Secure File Upload System running at http://{host}:{port}', flush=True)
    serve(create_app(), host=host, port=port, threads=4,
          max_request_body_size=MAX_FILE + MAX_REQUEST_OVERHEAD)
