#!/bin/bash

# Eseguo prima questo comando e dopo l'entrypoint originale dell'immagine di erddap
mkdir /var/www/html/frontend/logs
mkdir /datasets_xml_parts/active

rm -f /var/www/html/frontend/multipass-dev.cfg

sed -i "s|ERDDAPTitlePlaceholder|$TITLE|g" /datasets_xml_parts/start.xml
sed -i "s|GEONETWORK_URL|$GEONETWORK_URL|g" /datasets_xml_parts/start.xml
sed -i "s|CMS_URL|$ERDDAP_baseUrl/erddap-cms|g" /datasets_xml_parts/start.xml
sed -i "s|BASE_URL|$ERDDAP_baseUrl|g" /datasets_xml_parts/start.xml

bash /datasets_xml_parts/compile_datasets_xml.sh

# The custom logo (content/erddap/images/logo.png) is bind-mounted per-deployment
# from the host, so it can't be baked into webapps/erddap/images/logo.png at
# image build time - it has to be copied here, at container start, once the
# bind mount is in place. webapps/erddap/images/ was made world-writable in the
# Dockerfile so this works under any non-root TOMCAT_USER_ID too.
# Tomcat re-deploys/extracts webapps/erddap AFTER this script hands off to
# /entrypoint.sh below, which wipes out a copy done here too early - so retry
# the copy for a while in the background until it survives.
( for i in $(seq 1 40); do
    sleep 3
    cp -f /usr/local/tomcat/content/erddap/images/logo.png /usr/local/tomcat/webapps/erddap/images/logo.png 2>/dev/null
  done ) &

cd /var/www/html/frontend
nohup gunicorn --bind 0.0.0.0:5000 --timeout 0 main:app &

exec /entrypoint.sh "$@"
