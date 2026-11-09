FROM erddap/erddap:v2.31.1 AS base

LABEL organization="ISP-CNR" \
      developers="Alice Cavaliere" \
      description="A web app for managing ERDDDAP instances"

RUN apt update
RUN apt install -y python3 python3-pip pkg-config libhdf5-dev gunicorn python3-gunicorn curl
RUN pip3 install --break-system-packages flask xmltodict debugpy flask_wtf Flask-Multipass requests authlib plotly numpy pkgconfig netcdf4 h5netcdf xarray pandas chardet flask_sqlalchemy passlib psycopg2-binary flask-simple-captcha erddapy Flask-Mail

# the base image's setenv.sh prints every ERDDAP_* variable at startup
# ("ERDDAP configured with:"), so ERDDAP_emailPassword and ERDDAP_flagKeyKey
# ended up in clear text in `docker logs`. Mask the values of any variable whose
# name looks secret, and fail the build if upstream changes that line.
RUN grep -q '^ERDDAP_CONFIG=$(env ' /usr/local/tomcat/bin/setenv.sh \
 && sed -i '/^ERDDAP_CONFIG=$(env /a ERDDAP_CONFIG=$(echo "$ERDDAP_CONFIG" | sed -E "s/^(ERDDAP_[^=]*(password|Password|key|Key|secret|Secret|token|Token)[^=]*)=.*/\\1=***/")' /usr/local/tomcat/bin/setenv.sh \
 && grep -q '^ERDDAP_CONFIG=$(echo ' /usr/local/tomcat/bin/setenv.sh

# make tomcat access logs print the X-Forwarded-For header to get the real client IP instead of the reverse proxy one.
COPY custom/server.xml /usr/local/tomcat/conf/server.xml
# to read MySQL databases with EDDTableFromDatabase, add the MySQL JDBC driver here:
# COPY custom/mysql-connector-java.jar /usr/local/tomcat/webapps/erddap/WEB-INF/lib/mysql-connector-java.jar
COPY custom/datasets_xml_parts /datasets_xml_parts

# since I renamed the logo from noaab.png to logo.png in the datasets.xml, to prevent a "File not found" error I will rename this file
RUN cp /usr/local/tomcat/webapps/erddap/images/noaab.png /usr/local/tomcat/webapps/erddap/images/logo.png

# webapps/erddap/images/ and its files are owned by root:root (dir 755, files
# 644) in the base image, but ERDDAP runs as TOMCAT_USER_ID/GROUP_ID (a
# non-root, deployment-chosen UID set at container start, so unknown at build
# time) - without this, ERDDAP's own startup copy of the custom logo
# (content/erddap/images/logo.png -> webapps/erddap/images/logo.png, which
# overwrites the existing logo.png file rather than unlinking it, so the FILE
# itself needs write permission too, not just the directory) fails with
# AccessDeniedException and the logo 404s until someone copies it in by hand.
RUN chmod -R o+rwX /usr/local/tomcat/webapps/erddap/images
RUN mkdir -p /datasets_data
RUN mkdir -p /datasets_xml_parts/active
RUN bash /datasets_xml_parts/compile_datasets_xml.sh

FROM base AS dev

  COPY my_entrypoint_dev.sh /
  RUN ["chmod", "+x", "/my_entrypoint_dev.sh"]
  ENTRYPOINT ["/my_entrypoint_dev.sh"]
  EXPOSE 8080 5000 5678

  CMD ["catalina.sh", "run"]

FROM base AS prod

  ARG CMS_VERSION="6.2.2"
  LABEL version="${CMS_VERSION}"
  ENV CMS_VERSION="${CMS_VERSION}"

  COPY frontend /var/www/html/frontend
  RUN rm -f /var/www/html/frontend/multipass-dev.cfg /var/www/html/frontend/multipass-local.cfg

  RUN pip3 install --break-system-packages gunicorn

  COPY my_entrypoint_prod.sh /
  RUN ["chmod", "+x", "/my_entrypoint_prod.sh"]
  ENTRYPOINT ["/my_entrypoint_prod.sh"]

  CMD ["catalina.sh", "run"]

FROM base AS no-multiauth

  ARG CMS_VERSION="1.3"
  LABEL version="${CMS_VERSION}"
  ENV CMS_VERSION="${CMS_VERSION}"

  COPY frontend /var/www/html/frontend
  RUN rm -f /var/www/html/frontend/multipass-dev.cfg /var/www/html/frontend/multipass-prod.cfg

  RUN pip3 install --break-system-packages gunicorn

  COPY my_entrypoint_prod.sh /
  RUN ["chmod", "+x", "/my_entrypoint_prod.sh"]
  ENTRYPOINT ["/my_entrypoint_prod.sh"]

  CMD ["catalina.sh", "run"]