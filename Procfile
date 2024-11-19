web: gunicorn canguinaProject.wsgi --log-file - --timeout 120 --workers 3
web: export REDIS_URL_PROD=redis://default:wUBywEGykeUAlfUB0VwXf3Eiw2lKYj8d@redis-17883.c114.us-east-1-4.ec2.redns.redis-cloud.com:17883 && gunicorn canguinaProject.wsgi --log-file - --timeout 120 --workers 3
