FROM erddap/erddap:v2.30.0 AS base

LABEL organization="ISP-CNR" \
      developers="Giulio Verazzo, Alice Cavaliere" \
      description="A web app for managing ERDDDAP instances"

RUN apt update
RUN apt install -y python3 python3-pip pkg-config libhdf5-dev curl
RUN pip3 install --break-system-packages flask xmltodict debugpy flask_wtf Flask-Multipass requests authlib plotly numpy pkgconfig netcdf4 h5netcdf xarray pandas chardet flask_sqlalchemy passlib psycopg2-binary flask-simple-captcha erddapy Flask-Mail

# TEMPORARY upstream patch: EDDTableFromMultidimNcFiles crashes
# ("NDimensionalIndex... shape=[...] has a value less than 1") reading/generating a
# datasets.xml for a NetCDF with two or more independent dimensions of size > 1 where
# no single variable spans all of them (e.g. two sensors on the same mooring sampling
# at different rates). Confirmed broken on v2.29.0/v2.30.0/v2.31.0 (works on the older
# v2.24 this CMS used to run). Fix not yet released upstream - tracked at
# https://github.com/ERDDAP/erddap/issues/556 and fixed (not yet merged) by
# https://github.com/ERDDAP/erddap/pull/568 (branch ChrisJohnNOAA:EDDTableMultidimBadFile,
# pinned commit below for reproducibility). Remove this block once that fix ships in a
# tagged ERDDAP release and this image is bumped to it.
RUN curl -fsSL -o /tmp/TableFromMultidimNcFile.java \
      "https://raw.githubusercontent.com/ChrisJohnNOAA/erddap/f0169b5cd8f9d6e8899cd6fb8f12b243dadcb7e7/WEB-INF/classes/gov/noaa/pfel/coastwatch/pointdata/TableFromMultidimNcFile.java" && \
    cd /usr/local/tomcat/webapps/erddap/WEB-INF && \
    javac -cp "classes:../../../lib/servlet-api.jar:lib/*" -d /tmp/build_out /tmp/TableFromMultidimNcFile.java && \
    cp /tmp/build_out/gov/noaa/pfel/coastwatch/pointdata/TableFromMultidimNcFile.class \
       /tmp/build_out/gov/noaa/pfel/coastwatch/pointdata/TableFromMultidimNcFile\$VarData.class \
       classes/gov/noaa/pfel/coastwatch/pointdata/ && \
    rm -rf /tmp/TableFromMultidimNcFile.java /tmp/build_out

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
