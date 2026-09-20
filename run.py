import os
from waitress import serve
from app import create_app

if __name__ == '__main__':
    port = int(os.getenv('PORT', '5000'))
    host = os.getenv('HOST', '127.0.0.1')
    print(f'Secure File Upload System running at http://{host}:{port}', flush=True)
    serve(create_app(), host=host, port=port, threads=4, max_request_body_size=6 * 1024 * 1024)
