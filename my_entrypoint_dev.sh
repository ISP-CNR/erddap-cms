#!/bin/bash

# Eseguo prima questo comando e dopo l'entrypoint originale dell'immagine di erddap
#mkdir /var/www/html/frontend/logs

#nohup python3 -m debugpy --wait-for-client --listen 0.0.0.0:5678 -m flask run --host=0.0.0.0 --debug > /var/www/html/frontend/logs/flask.log 2>&1 & 

mkdir /datasets_xml_parts/active

sed -i "s|ERDDAPTitlePlaceholder|$TITLE|g" /datasets_xml_parts/start.xml
sed -i "s|GEONETWORK_URL|$GEONETWORK_URL|g" /datasets_xml_parts/start.xml
sed -i "s|CMS_URL|$ERDDAP_baseUrl/erddap-cms|g" /datasets_xml_parts/start.xml
sed -i "s|BASE_URL|$ERDDAP_baseUrl|g" /datasets_xml_parts/start.xml

bash /datasets_xml_parts/compile_datasets_xml.sh

# see my_entrypoint_prod.sh for why this needs to retry in the background
( for i in $(seq 1 40); do
    sleep 3
    cp -f /usr/local/tomcat/content/erddap/images/logo.png /usr/local/tomcat/webapps/erddap/images/logo.png 2>/dev/null
  done ) &

#nohup python3 -m debugpy --wait-for-client --listen 0.0.0.0:5678 -m flask run --host=0.0.0.0 --debug &
nohup python3 -m debugpy --listen 0.0.0.0:5678 -m flask run --host=0.0.0.0 --debug &
exec /entrypoint.sh "$@"
