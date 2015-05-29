#!/bin/bash

if [ "${SSL_CERT}" = "**None**" ]; then
    unset SSL_CERT
fi

if [ "${BACKEND_PORTS}" = "**None**" ]; then
    unset BACKEND_PORTS
fi

if [ -n "$SSL_CERT" ]; then
    echo "SSL certificate provided!"
    echo -e "${SSL_CERT}" > /servercert.pem
    export SSL="ssl crt /servercert.pem"
else
    echo "No SSL certificate provided"
fi

exec python /app/haproxy.py 
