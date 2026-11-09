"""
Tests for the helpers that make DasDds's output readable in the validation modal.

The log tails below are real, from running DasDds (ERDDAP 2.31.1) on broken
datasets, shortened: the cause comes right before the "load failed" marker and
often has no ERROR prefix.
"""
import os

# utils.py reads these at import time
os.environ.setdefault("URL_PATH", "")
os.environ.setdefault("ERDDAP_baseUrl", "http://localhost:8080/erddap")
os.environ.setdefault("PUBLISHER_NAME", "Test Publisher")
os.environ.setdefault("PUBLISHER_URL", "http://example.org")

import utils

STARTUP = """////**** EDStatic Low Level Startup
got emailUserName from ERDDAP_emailUserName
*** EDStatic Low Level Startup finished successfully.

*** Starting DasDds 2026-11-03T14:27:49+00:00 erddapVersion=2.31.1
*** constructing EDDTableFromFiles test_dataset
"""

CRASH = """
*** An error occurred while trying to load test_dataset:
java.lang.NullPointerException: Cannot invoke "EDD.makeNewFileForDapQuery" because "edd" is null
 at gov.noaa.pfel.erddap.DasDds.main(DasDds.java:187)


*** closed logFile=/erddapData/logs/DasDds.log at 2026-11-03T14:27:50+00:00
"""


def failure(cause):
    return STARTUP + cause + "\n" + CRASH


def summarize(cause):
    return utils.summarize_validation_error(failure(cause))


def test_duplicate_fixed_value_is_decoded_with_coordinates_hint():
    summary = summarize('nReadFile=1\nERROR: Invalid Table: Duplicate column names: [22] and [23] are both "x3dx2245x22".')

    assert summary["line"] == 'ERROR: Invalid Table: Duplicate column names: [22] and [23] are both "="45"".'
    assert summary["title"] == 'Two variables have the same sourceName: ="45"'
    assert "latitude and longitude" in summary["hint"]


def test_duplicate_regular_column_does_not_mention_coordinates():
    summary = summarize('ERROR: Invalid Table: Duplicate column names: [1] and [2] are both "max20".')

    assert summary["title"] == "Two variables have the same sourceName: max20"
    assert "latitude" not in summary["hint"]


def test_cause_without_error_prefix_is_found():
    summary = summarize("ftLastMod first=2026\nFor cdm_data_type=TimeSeries, the global attribute cdm_timeseries_variables must be set.")

    assert summary == {
        "title": None,
        "line": "For cdm_data_type=TimeSeries, the global attribute cdm_timeseries_variables must be set.",
        "hint": None,
    }


def test_generic_error_heading_is_not_mistaken_for_the_cause():
    summary = summarize("ERROR in Test.ensureSomethingUnicode():\ndatasets.xml/EDD.ensureValid error for datasetID=x:\n title wasn't set.")

    assert summary["line"] == "title wasn't set."


def test_no_files_points_at_the_files_found_line():
    summary = summarize("0 files found in /datasets_data/x/\nregex=.* recursive=true pathRegex=.* time=2ms")

    assert summary["title"] == "No data files found"
    assert summary["line"] == "0 files found in /datasets_data/x/"


def test_multiline_message_uses_its_meaningful_line():
    summary = summarize('Unknown <sortFilesBySourceNames> name#0="nope"\nsourceDataNames=time, temp')

    assert summary["title"] == "sortFilesBySourceNames names an unknown variable: nope"
    assert summary["line"] == 'Unknown <sortFilesBySourceNames> name#0="nope"'


def test_time_units_are_explained():
    summary = summarize("ERROR in Test.ensureTrue:\n dataVariable[timeIndex=0] isn't an EDVTime.")

    assert summary["title"] == "The time variable has invalid units"


def test_xml_parse_failure_reports_the_exception_after_the_marker():
    log = STARTUP + """
*** An error occurred while trying to load test_dataset:
org.xml.sax.SAXParseException; lineNumber: 6844; columnNumber: 18; The end-tag for element type "addAttributes" must end with a '>' delimiter.
 at java.xml/com.sun.org.apache.xerces.internal.util.ErrorHandlerWrapper.fatalError(ErrorHandlerWrapper.java:178)
"""
    summary = utils.summarize_validation_error(log)

    assert summary["title"] == "The XML isn't well formed"
    assert "lineNumber: 6844" in summary["line"]


def test_stack_frame_before_the_marker_is_not_a_cause():
    assert summarize(" at gov.noaa.pfel.erddap.DasDds.main(DasDds.java:187)") is None


def test_log_without_the_marker_returns_none():
    assert utils.summarize_validation_error("ERROR: something\njava.lang.RuntimeException: boom") is None


def test_names_that_only_look_encoded_are_left_alone():
    line = 'ERROR: bad column "max20" and "x3dx22ax22"'

    assert utils.decode_erddap_names(line) == 'ERROR: bad column "max20" and "="a""'


def test_trim_removes_startup_and_keeps_the_rest():
    trimmed = utils.trim_dasdds_startup(failure("some cause"))

    assert trimmed.startswith("*** Starting DasDds")
    assert "got emailUserName" not in trimmed
    assert "NullPointerException" in trimmed


def test_trim_without_marker_returns_output_unchanged():
    assert utils.trim_dasdds_startup("no marker here") == "no marker here"
