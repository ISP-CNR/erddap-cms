FROM axiom/docker-erddap:2.24-jdk21-openjdk AS base

LABEL organization="ISP-CNR" \
      developers="Giulio Verazzo, Alice Cavaliere" \
      description="A web app for managing ERDDDAP instances"

RUN apt update
RUN apt install -y python3 python3-pip pkg-config libhdf5-dev
RUN pip3 install flask xmltodict debugpy flask_wtf Flask-Multipass requests authlib plotly numpy pkgconfig netcdf4 h5netcdf xarray pandas pexpect chardet flask_sqlalchemy passlib psycopg2-binary flask-simple-captcha erddapy Flask-Mail

COPY custom/datasets_xml_parts /datasets_xml_parts

# since I renamed the logo from noaab.png to logo.png in the datasets.xml, to prevent a "File not found" error I will rename this file
RUN cp /usr/local/tomcat/webapps/erddap/images/noaab.png /usr/local/tomcat/webapps/erddap/images/logo.png
RUN mkdir -p /datasets_data
RUN mkdir -p /datasets_xml_parts/active
RUN bash /datasets_xml_parts/compile_datasets_xml.sh

FROM base AS dev

  COPY my_entrypoint.sh /
  RUN ["chmod", "+x", "/my_entrypoint.sh"]
  ENTRYPOINT ["/my_entrypoint.sh"]
  EXPOSE 8080 5000 5678

  CMD ["catalina.sh", "run"]