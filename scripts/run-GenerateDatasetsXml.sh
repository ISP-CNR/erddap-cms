docker exec -it \
  erddap-cms \
  bash -c "cd /usr/local/tomcat/webapps/erddap/WEB-INF/; java -cp classes:../../../lib/servlet-api.jar:lib/* -Xms1000M -Xmx1000M gov.noaa.pfel.erddap.GenerateDatasetsXml"


