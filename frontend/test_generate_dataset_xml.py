"""
Tests for generate_dataset_xml() and its per-EDDType argument builders.

These do NOT run the real `GenerateDatasetsXml` Java tool (that needs a full
ERDDAP/Tomcat install) - they build a real CSV and a real NetCDF file on disk,
mock subprocess.run and the GenerateDatasetsXml.out log file, and assert that
the command line we build is the one GenerateDatasetsXml expects for each
EDDType, in the same order as its interactive prompts.
"""
import os

# utils.py reads these at import time
os.environ.setdefault("URL_PATH", "")
os.environ.setdefault("ERDDAP_baseUrl", "http://localhost:8080/erddap")
os.environ.setdefault("PUBLISHER_NAME", "Test Publisher")
os.environ.setdefault("PUBLISHER_URL", "http://example.org")

import shlex
from unittest.mock import patch, MagicMock

import netCDF4 as nc
import pytest

import utils


@pytest.fixture
def csv_file(tmp_path):
    path = tmp_path / "sample.csv"
    path.write_text(
        "time,lat,lon,temperature\n"
        "2024-01-01T00:00:00Z,45.0,10.0,12.3\n"
        "2024-01-01T01:00:00Z,45.0,10.0,12.5\n"
        "2024-01-01T02:00:00Z,45.0,10.0,12.7\n"
    )
    return str(path)


@pytest.fixture
def netcdf_multidim_file(tmp_path):
    path = tmp_path / "sample.nc"
    with nc.Dataset(path, "w", format="NETCDF4") as ds:
        ds.createDimension("obs", 3)
        ds.createDimension("station", 1)
        var = ds.createVariable("temperature", "f4", ("obs",))
        var[:] = [1.0, 2.0, 3.0]
    return str(path)


def _mock_success_run(log_path, log_contents="<dataset>fake</dataset>"):
    """Patch subprocess.run to look like a successful GenerateDatasetsXml run,
    and pre-write the log file it's expected to read afterwards."""
    with open(log_path, "w") as f:
        f.write(log_contents)
    completed = MagicMock()
    completed.stdout = "...\ngenerateDatasetsXml finished successfully\n"
    completed.stderr = ""
    return completed


class TestGenerateDatasetXmlAscii:
    def test_builds_expected_args_and_returns_log_content(self, tmp_path, csv_file):
        log_path = tmp_path / "GenerateDatasetsXml.out"

        with patch.object(utils, "GENERATE_DATASETS_XML_LOG", str(log_path)), \
             patch("subprocess.run") as mock_run:
            mock_run.return_value = _mock_success_run(str(log_path), "<dataset>ascii</dataset>")

            xml = utils.generate_dataset_xml(
                csv_file, "My Title", "My Summary", "My Institution",
                "http://example.org", "Point", quiet=True,
            )

        assert xml == "<dataset>ascii</dataset>"

        # inspect the bash -c command actually built
        assert mock_run.call_count == 1
        (call_args,), call_kwargs = mock_run.call_args
        assert call_args[0] == "bash"
        assert call_args[1] == "-c"
        command = call_args[2]
        assert "gov.noaa.pfel.erddap.GenerateDatasetsXml" in command

        java_args = shlex.split(command.split("GenerateDatasetsXml", 1)[1])
        assert java_args[0] == "EDDTableFromAsciiFiles"
        assert java_args[1] == os.path.dirname(csv_file)
        assert java_args[2] == ""          # file name regex
        assert java_args[3] == csv_file
        # infoUrl/institution/summary/title must appear, in the ascii-prompt order
        assert "http://example.org" in java_args
        assert "My Institution" in java_args
        assert "My Summary" in java_args
        assert "My Title" in java_args

    def test_raises_when_generate_datasets_xml_fails(self, tmp_path, csv_file):
        log_path = tmp_path / "GenerateDatasetsXml.out"
        with patch.object(utils, "GENERATE_DATASETS_XML_LOG", str(log_path)), \
             patch("subprocess.run") as mock_run:
            failed = MagicMock()
            failed.stdout = "some unexpected error\n"
            failed.stderr = ""
            mock_run.return_value = failed

            with pytest.raises(Exception, match="generateDatasetsXml unknown error"):
                utils.generate_dataset_xml(
                    csv_file, "T", "S", "I", "http://x", "Point", quiet=True,
                )


class TestGenerateDatasetXmlMultidimNc:
    def test_builds_expected_args(self, tmp_path, netcdf_multidim_file):
        log_path = tmp_path / "GenerateDatasetsXml.out"

        with patch.object(utils, "GENERATE_DATASETS_XML_LOG", str(log_path)), \
             patch("subprocess.run") as mock_run:
            mock_run.return_value = _mock_success_run(str(log_path), "<dataset>nc</dataset>")

            xml = utils.generate_dataset_xml(
                netcdf_multidim_file, "T", "S", "Inst",
                "http://info", "TimeSeries", quiet=True,
            )

        assert xml == "<dataset>nc</dataset>"

        command = mock_run.call_args[0][0][2]
        java_args = shlex.split(command.split("GenerateDatasetsXml", 1)[1])
        assert java_args[0] == "EDDTableFromMultidimNcFiles"
        assert java_args[3] == netcdf_multidim_file
        # dimensionsCSV (first type-specific arg) must list only dimensions with
        # size > 1: a size-1 dim (like "station" here) isn't a real row dimension
        # and confuses GenerateDatasetsXml if included (NDimensionalIndex crash)
        dimensions_csv = java_args[4]
        assert set(dimensions_csv.split(",")) == {"obs"}


@pytest.fixture
def netcdf_with_size1_dim_file(tmp_path):
    # mirrors a real-world file: a "depth" dimension of size 1 holding a single
    # station-level value, alongside the real "obs" (time) dimension
    path = tmp_path / "sample_size1dim.nc"
    with nc.Dataset(path, "w", format="NETCDF4") as ds:
        ds.createDimension("obs", 3)
        ds.createDimension("depth", 1)
        temp = ds.createVariable("temperature", "f4", ("obs",))
        temp[:] = [1.0, 2.0, 3.0]
        depth = ds.createVariable("depth", "f8", ("depth",))
        depth.standard_name = "depth"
        depth.units = "m"
        depth[:] = [1010.94]
    return str(path)


class TestGetLowCardinalityColumns:
    def test_finds_categorical_columns_by_real_cardinality(self, tmp_path):
        path = tmp_path / "species.csv"
        path.write_text(
            "time,station,species,plot,measurement\n"
            "2024-01-01,CCT,Dryas,1,1.1\n"
            "2024-01-02,CCT,Salix,2,1.2\n"
            "2024-01-03,CCT,Dryas,3,1.3\n"
            "2024-01-04,CCT,Salix,4,1.4\n"
        )
        columns = utils.get_low_cardinality_columns(str(path))
        # station: 1 distinct value -> not useful as a filter, excluded
        # species: 2 distinct values, varies within the file -> included
        # plot: 4 distinct values (== n_rows) -> effectively unique, excluded
        # measurement, time: unique per row -> excluded
        assert columns == ["species"]

    def test_returns_empty_for_netcdf(self, netcdf_multidim_file):
        assert utils.get_low_cardinality_columns(netcdf_multidim_file) == []


class TestDroppedScalarDataVariables:
    def test_reinjects_variable_whose_only_dim_was_excluded(self, netcdf_with_size1_dim_file):
        dropped = utils._dropped_scalar_dataVariables(netcdf_with_size1_dim_file, existing_names={"temperature"})

        assert len(dropped) == 1
        depth_var = dropped[0]
        assert depth_var["destinationName"] == "depth"
        assert depth_var["sourceName"] == '="1010.94"'
        assert depth_var["dataType"] == "double"
        assert {"standard_name": "depth", "units": "m"} == {
            a["@name"]: a["#text"] for a in depth_var["addAttributes"]["att"]
        }

    def test_skips_variable_already_present(self, netcdf_with_size1_dim_file):
        dropped = utils._dropped_scalar_dataVariables(
            netcdf_with_size1_dim_file, existing_names={"temperature", "depth"},
        )
        assert dropped == []

    def test_fix_generated_xml_reinjects_missing_depth(self, netcdf_with_size1_dim_file):
        # a generated XML that (as GenerateDatasetsXml would) only has "temperature",
        # missing "depth" because its only dimension was excluded from dimensionsCSV
        fake_xml = f'''<dataset type="EDDTableFromMultidimNcFiles" datasetID="x">
    <fileDir>/tmp/</fileDir>
    <addAttributes></addAttributes>
    <dataVariable>
        <sourceName>temperature</sourceName>
        <destinationName>temperature</destinationName>
        <dataType>float</dataType>
        <addAttributes></addAttributes>
    </dataVariable>
</dataset>'''

        fixed = utils.fix_generated_xml(
            fake_xml, "dsid", "myDataset", "TimeSeries", "Alice", "a@a.com",
            '="0.0"', '="0.0"', "/datasets_data/dsid/", "Inst", "http://info",
            netcdf_with_size1_dim_file,
        )

        assert "<destinationName>depth</destinationName>" in fixed
        assert '<sourceName>="1010.94"</sourceName>' in fixed


class TestGenerateDatasetXmlGridNc:
    def test_builds_expected_args(self, tmp_path, netcdf_multidim_file):
        log_path = tmp_path / "GenerateDatasetsXml.out"

        with patch.object(utils, "GENERATE_DATASETS_XML_LOG", str(log_path)), \
             patch("subprocess.run") as mock_run:
            mock_run.return_value = _mock_success_run(str(log_path), "<dataset>grid</dataset>")

            xml = utils.generate_dataset_xml(
                netcdf_multidim_file, "T", "S", "Inst",
                "http://info", "Grid", quiet=True,
            )

        assert xml == "<dataset>grid</dataset>"

        command = mock_run.call_args[0][0][2]
        java_args = shlex.split(command.split("GenerateDatasetsXml", 1)[1])
        assert java_args[0] == "EDDGridFromNcFiles"
