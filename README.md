# ERDDAP-CMS

[ERDDAP™](https://github.com/ERDDAP/erddap) is a data server that gives you a simple, consistent way to download subsets of gridded and tabular scientific datasets in common file formats and make graphs and maps.

## Why

ERDDAP™ itself manages datasets through a single hand-edited `datasets.xml` file plus a command-line tool (`GenerateDatasetsXml`) and a reload flag mechanism - powerful, but it requires ERDDAP-specific expertise and comfort editing raw XML. ERDDAP-CMS was built so that researchers who know their data, not ERDDAP internals, can publish a dataset themselves: upload a file, fill in a web form, and let the CMS handle metadata conventions (ACDD/CF), validation, and per-dataset access control on top of it.

ERDDAP-CMS is web-app that aims to simplify the usage and management of ERDDAP data server. Main features are:

  - Upload of new datasets from CSV, netCDF or other ERDDAP instances
  - Complete ACDD-based metadata editor
  - Metadata keywords from CF-convention standard names table
  - One-click dataset validation and publication
  - ORCID, GitHub, OAuth login (Contact us for more info about this)
  - ISO 19139 (gmd prefix) metadata export fully compatibile with GeoNetwork Opensource
  - Management of user permissions on dataset
  - The list of institutions is sourced from the Research Organization Registry (ROR).

See [docs/DATASET_WORKFLOW.md](docs/DATASET_WORKFLOW.md) for the dataset upload/publish workflow. Complete documentation is under development.

## Development

ERDDAP-CMS is a Python Flask application and resides in the `frontend/` folder.

To launch it, use the `docker-compose.yml` file by running the command:

`docker compose up -d`

- ERDDAP is available at http://server-host:8080/erddap  
- ERDDAP-CMS is available at http://server-host:5000/erddap-cms

The default credentials for the admin user in the CMS are:
- username: `admin`
- password: `admin`

## How dataset creation works

See [docs/DATASET_WORKFLOW.md](https://github.com/ISP-CNR/erddap-cms/blob/main/docs/DATASET_WORKFLOW.md) for the full creation and publication of the dataset. Under the hood, each dataset is still just an ERDDAP `<dataset>` XML definition - the CMS automates producing, checking, and maintaining it:

1. **Draft generation.** On upload, the CMS calls ERDDAP's own `GenerateDatasetsXml` command-line tool with every one of its interactive prompts pre-filled as command-line arguments (so it runs fully non-interactively, no scripted terminal session needed) to draft the initial XML - `EDDTableFromAsciiFiles` for CSV, `EDDTableFromMultidimNcFiles` or `EDDGridFromNcFiles` for NetCDF, depending on the chosen dataset type.
2. **Post-processing.** The CMS then adjusts that draft based on the dataset type chosen: for **Time Series** / **Time Series Profile**, it injects `cf_role="timeseries_id"` where a station column is detected and synthesizes a `station_id` variable when none exists; **Time Series Profile** additionally requires a "time"-like column (set as `cf_role="profile_id"`) and a "depth"-like column (used as `cdm_altitude_proxy` if not literally named `depth`), failing the upload if either is missing; for every type it also applies CF standard-name/ACDD metadata defaults (creator, institution, publisher info, `cdm_data_type`, etc.).
3. **Storage.** Each dataset's XML is kept as its own file under `custom/datasets_xml_parts/active/`, independent from every other dataset.
4. **Validate.** This runs ERDDAP's own `DasDds.sh` script directly against that one dataset's definition - the same check ERDDAP performs when actually loading a dataset - without touching the live `datasets.xml`. Any error ERDDAP reports (missing required attribute, malformed value, etc.) is parsed and shown back in the edit page; the dataset is only marked valid once this succeeds with no errors.
5. **Publish/Reload.** Concatenates every active dataset's XML file (plus `start.xml`/`end.xml`/`users.xml`) into ERDDAP's single `datasets.xml` and triggers ERDDAP's own reload flag, so it picks up the change without a full server restart.

## How users work

CMS accounts are separate from ERDDAP's own user system - see [docs/DATASET_WORKFLOW.md](docs/DATASET_WORKFLOW.md#2-as-an-admin) for the admin side of managing them. A few things worth knowing:

- **Login** supports multiple providers (local email/password, ORCID, GitHub, CNR - contact us for details), all layered on top of the same account via [Flask-Multipass](https://github.com/indico/flask-multipass).
- **New accounts start inactive.** Registering (captcha-protected) notifies an admin by email, but the account can't do anything until an admin flips it active from the Users page - this is the CMS's approval gate.
- **Two roles**: admin and regular user. Admins can access and edit every dataset, manage other accounts, and are the only ones who can enable a dataset on ERDDAP (see the "Enable dataset" note in [docs/DATASET_WORKFLOW.md](docs/DATASET_WORKFLOW.md)). Regular users only see/edit datasets they've been explicitly granted access to.
- **Per-dataset CMS permissions** are separate from ERDDAP's own `accessibleTo` roles used for private datasets - the former controls who can edit a dataset in the CMS, the latter controls who can download its raw data on ERDDAP itself.

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
