# Dataset workflow: from upload to publication

This document describes the full lifecycle of a dataset in ERDDAP-CMS, from the moment a
user uploads a file to the moment it's live on ERDDAP - covering both what a regular user
does and what only an admin can do.

For a more visual, click-by-click walkthrough, logged-in users can also open the in-app
**Guide** (top nav bar, or the "Guide" button next to "Add new dataset").

## 1. As a user

### 1.1 Start the upload

From the dataset list, click **Add new dataset**, then choose:

- **From existing file** - the common case, described below.
- **From another ERDDAP** - paste the URL of a dataset already published on a different
  ERDDAP instance to pull in its existing definition instead of starting from a raw data
  file.

### 1.2 Upload a file

A dataset is built from one or more data files in `.csv`, `.nc` (NetCDF-3) or `.h5` (HDF5)
format. Upload one file to start - more can be added to the same dataset later.

- Dates/times in a CSV file must use the format `yyyy-MM-ddTHH:mm:ssZ`.
- NetCDF/HDF5 files that already carry proper metadata (COARDS/CF/ACDD conventions) need
  the least manual work afterwards, since the CMS reads titles, variable names and
  attributes straight from the file.
- A CSV file has no way to carry a title or summary, so the form asks for those directly
  when it detects one.

### 1.3 Pick the dataset type

This tells ERDDAP how to interpret the file's rows/dimensions:

- **Time Series** - repeated measurements over time at a fixed latitude/longitude/depth.
- **Time Series Profile** - repeated profiles (multiple depths/altitudes) over time at a
  fixed location.
- **Grid** - gridded data (e.g. satellite imagery, model output) with regular
  latitude/longitude/time axes.
- **Other** - no requirements; use this if the dataset doesn't have latitude, longitude
  and time variables, or doesn't fit the other options.

The common case is the simplest one: one file, one station, a single fixed
latitude/longitude for the whole dataset. If the file has no station column at all, the
CMS adds one automatically (a `station_id` variable) and treats the whole file as one
single station.

A single Time Series (or Time Series Profile) dataset can also hold data from **many
different stations**, as long as the file has a column identifying which station each row
belongs to (same latitude/longitude repeated for every row of the same station).

- For a **CSV**, the CMS decides which column identifies the station by its name: any
  column containing "station" (e.g. `Station_ID`). Under the hood this sets
  `cf_role="timeseries_id"` on that variable in the dataset's XML definition - it can't be
  set manually from the edit page (only an admin can, via the XML tab), so renaming the
  column and re-uploading is the way to fix a station column that wasn't picked up.
- A **NetCDF** file gets an extra, more reliable path: if it already declares
  `cf_role="timeseries_id"` natively on some variable - whatever it's named - the CMS uses
  that directly, and the name-matching rule above is only a fallback. Likewise, if the
  file already declares a supported CF featureType, the CMS trusts that over whatever
  dataset type is picked in the form.

### 1.4 Fill in the initial fields

- **Title / Summary** - only asked for CSV files, which can't carry them internally.
- **Creator email** - defaults to the uploader's own account email. This is the address
  that later receives the "your dataset was enabled" notification (see 2.3), so it should
  be a real, monitored inbox.
- **Info URL** - a web page with more information about the dataset or the institution.
- **Institution** - start typing to search; results come from
  [ROR](https://ror.org), the public registry of research organizations.
- **Latitude / Longitude** - only shown if the file doesn't already contain valid
  coordinates.

Clicking **Ok** makes the CMS read the file, auto-generate a first draft of the dataset's
full metadata (variables, data types, attributes) and create the dataset. It lands back on
the dataset list, not yet Validated or Published - that's expected, the next steps finish
the job.

### 1.5 Finish the metadata

Open the new dataset (its gear icon in the Actions column - its name links to ERDDAP
itself, not the edit page). Fields marked with `*` are required: things like
`institution`, `summary`, `history`, `Conventions`, `license`, `creator_name`/
`creator_email`, `contributor_name`/`contributor_email`/`contributor_institution` and
`standard_name_vocabulary`. Most are pre-filled with reasonable defaults - check them
rather than assuming they're right for this dataset.

Each variable also has two descriptive attributes worth checking:

- **long_name** - free text, whatever human-readable label is wanted (e.g. "Sea Water
  Temperature"). Shown as-is in plots and other tools.
- **standard_name** - not free text: it's a fixed, machine-readable term from a
  controlled vocabulary (the CMS bundles the CF v1.6 standard names table), so other
  tools can recognize e.g. "this column is sea water temperature" automatically. Not
  strictly required, but worth filling in where one applies.

### 1.6 Private dataset (optional)

If the data shouldn't be publicly downloadable yet (e.g. under embargo), toggle
**Private dataset** on the edit page before publishing - the title, summary and graphs
stay visible to everyone on ERDDAP, only the raw data requires a login. This can be
changed at any time later. Private datasets need at least one user or role granted access
(see 2.4).

### 1.7 Save, Validate, Publish

Same three steps for every change, new dataset or not:

1. **Save** the changes.
2. **Validate** them - ERDDAP checks the metadata is correct. Fix anything it flags and
   validate again.
3. **Publish** (or **Reload**, once already published) to make it live on ERDDAP.

A brand new dataset starts out **disabled**, and only an admin can enable it (see 2.2).
Because of this, a non-admin user validating a new dataset sees the button read
**Request publish** instead of Publish - clicking it notifies an admin to come enable the
dataset, instead of doing a reload that would have no visible effect. The dataset's
creator gets an email once an admin enables it.

## 2. As an admin

Everything in section 1 also applies to admins - the differences below are the actions
only an admin can take.

### 2.1 Enable / disable a dataset

The **Enable dataset** switch on the edit page controls the dataset's `active` attribute
in ERDDAP. A disabled dataset is **never shown on ERDDAP, even if it's already validated
and published** - this is the actual gate that decides whether a dataset is publicly
reachable. Save + Publish/Reload only push the current XML definition to ERDDAP; they
don't affect this switch.

### 2.2 Handling publish requests

When a non-admin user clicks **Request publish** on a validated, disabled dataset:

- An email is sent to the admin notification address (`ERDDAP_emailEverythingTo`),
  naming the requesting user, the dataset title and id.
- The dataset is flagged internally (`publish_requested` in the database) so the same
  user clicking again doesn't send duplicate emails - they instead see
  "Publish requested" with a tooltip explaining an admin was already notified.

To act on a request: open the dataset's edit page, turn on **Enable dataset**, Save, then
Publish. Once the dataset transitions from disabled to enabled this way, the CMS
automatically:

- emails the dataset's `creator_email` (not necessarily the requesting user's own login
  email - the field set in step 1.4) with the dataset's title, id, summary, institution
  and creator, plus a link back to its edit page,
- clears the `publish_requested` flag, so a future disable/re-request cycle can notify
  again.

If a dataset is enabled without ever having had a publish request (e.g. an admin's own
new dataset), no such email is sent - there's no request to fulfill.

### 2.3 Managing users

The **Users** page (admin only) lists every CMS account, grouped into Admins and Users,
with each user's permissions shown as expandable cards:

- Admins implicitly have access to every dataset - the CMS doesn't store or display a
  permission list for them.
- Regular users show the datasets and ERDDAP roles explicitly granted to them, by
  dataset title (not just its raw id).

From here an admin can grant or revoke access to private datasets on a per-user or
per-role basis, and promote/demote admin status.

### 2.4 Per-dataset access control (private datasets)

For a dataset marked **Private**, access is controlled per ERDDAP user/role rather than
per CMS account - a CMS user's access to the raw data depends on their ERDDAP identity,
via the `accessibleTo` / `graphsAccessibleTo` dataset attributes. Assign roles/users to a
private dataset from its edit page; that assignment is what needs to exist before Save +
Publish/Reload actually restricts the data.

Note the same caveat as in 1.6: toggling privacy or its role assignments only takes
effect on ERDDAP after Validate + Publish/Reload - Save alone only writes the local XML.
The edit page shows a warning banner when a private dataset hasn't actually been pushed
live yet, since an out-of-date `accessibleTo` is a false-sense-of-security risk.
