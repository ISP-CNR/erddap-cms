# ERDDAP-CMS

ERDDAP is a data server that gives you a simple, consistent way to download subsets of gridded and tabular scientific datasets in common file formats and make graphs and maps.

ERDDAP-CMS is web-app that aims to simplify the usage and management of ERDDAP data server. Main features are:

  - Upload of new datasets from CSV, netCDF or other ERDDAP instances
  - Complete ACDD-based metadata editor
  - Metadata keywords from CF-convention standard names table
  - One-click dataset validation and publication
  - ORCID, GitHub, OAuth login (Contact us for more info about this)
  - ISO 19139 (gmd prefix) metadata export fully compatibile with GeoNetwork Opensource
  - Management of user permissions on dataset

Complete documentation is under development.

## Development

ERDDAP-CMS is a Python Flask application and resides in the `frontend/` folder.

To launch it, use the `docker-compose.yml` file by running the command:

`docker compose up -d`

- ERDDAP is available at http://server-host:8080/erddap  
- ERDDAP-CMS is available at http://server-host:5000/erddap-cms

The default credentials for the admin user in the CMS are:
- username: `admin`
- password: `admin`

## Miscellaneous

Datasets configuration files and data are not tracked by git.
Data is saved inside the docker volume `datasets_data` while datasets configuration files are stored in `datasets_xml` folder

## Authors and acknowledgment
The project main authors are:

  - [Giulio Verazzo, Italian Institute of Polar Sciences](mailto:giulio.verazzo@cnr.it)
  - [Alice Cavaliere, Italian Institute of Polar Sciences](mailto:alice.cavaliere@cnr.it)

## License
This code is licensed under GPLv3

## Project status
Under development