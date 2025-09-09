#!/bin/bash

mkdir /datasets_xml_parts/active

sed -i "s|ERDDAPTitlePlaceholder|$TITLE|g" /datasets_xml_parts/start.xml
sed -i "s|GEONETWORK_URL|$GEONETWORK_URL|g" /datasets_xml_parts/start.xml
sed -i "s|CMS_URL|$ERDDAP_baseUrl/erddap-cms|g" /datasets_xml_parts/start.xml
sed -i "s|BASE_URL|$ERDDAP_baseUrl|g" /datasets_xml_parts/start.xml

bash /datasets_xml_parts/compile_datasets_xml.sh

nohup python3 -m flask run --host=0.0.0.0 --debug &

exec /entrypoint.sh "$@"