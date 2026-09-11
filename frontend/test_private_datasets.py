"""
Tests for the private-dataset feature: the ERDDAP UEPMD5 password hash,
the users.xml generation, and get_private_dataset_roles() (the role picker
shown on the ERDDAP user form).

These don't need a running Flask app/DB - write_erddap_users_xml() and
get_erddap_users() are exercised through a small fake in place of the
multiauth module, and get_private_dataset_roles() reads real (temporary)
dataset XML files from disk, same pattern as test_generate_dataset_xml.py.
"""
import os

# utils.py reads these at import time
os.environ.setdefault("URL_PATH", "")
os.environ.setdefault("ERDDAP_baseUrl", "http://localhost:8080/erddap")
os.environ.setdefault("PUBLISHER_NAME", "Test Publisher")
os.environ.setdefault("PUBLISHER_URL", "http://example.org")

import hashlib
from types import SimpleNamespace
from unittest.mock import patch

import pytest

import utils


class TestErddapPasswordHash:
    def test_matches_uepmd5_formula(self):
        # ERDDAP's UEPMD5 passwordEncoding: MD5("username:ERDDAP:password")
        expected = hashlib.md5(b"alice:ERDDAP:hunter2").hexdigest()
        assert utils.erddap_password_hash("alice", "hunter2") == expected

    def test_different_usernames_give_different_hashes(self):
        # same password, different username -> the hash must differ (the
        # username is part of the hashed string, not just a lookup key)
        assert utils.erddap_password_hash("alice", "samepw") != \
               utils.erddap_password_hash("bob", "samepw")

    def test_is_32_hex_chars(self):
        h = utils.erddap_password_hash("alice", "hunter2")
        assert len(h) == 32
        int(h, 16)  # raises ValueError if not valid hex


class TestWriteErddapUsersXml:
    def test_writes_expected_user_elements(self, tmp_path):
        users_path = tmp_path / "users.xml"
        fake_users = [
            SimpleNamespace(username="alice", password_hash="abc123", roles="IADC,GUESTS"),
            SimpleNamespace(username="bob", password_hash="def456", roles=""),
        ]
        fake_multiauth = SimpleNamespace(get_erddap_users=lambda: fake_users)

        with patch.object(utils, "ERDDAP_USERS_XML", str(users_path)), \
             patch.dict("sys.modules", {"multiauth": fake_multiauth}):
            utils.write_erddap_users_xml()

        content = users_path.read_text()
        assert '<user username="alice" password="abc123" roles="IADC,GUESTS"/>' in content
        assert '<user username="bob" password="def456" roles=""/>' in content

    def test_escapes_attribute_special_characters(self, tmp_path):
        # a username/role containing XML-significant characters must not be
        # able to break out of the attribute (e.g. inject a bogus "roles=" or
        # a whole new <user> element)
        users_path = tmp_path / "users.xml"
        fake_users = [
            SimpleNamespace(username='mallory" roles="ADMIN', password_hash="x", roles="R&D"),
        ]
        fake_multiauth = SimpleNamespace(get_erddap_users=lambda: fake_users)

        with patch.object(utils, "ERDDAP_USERS_XML", str(users_path)), \
             patch.dict("sys.modules", {"multiauth": fake_multiauth}):
            utils.write_erddap_users_xml()

        content = users_path.read_text()
        # the malicious username must appear as escaped attribute text, not
        # as literal unescaped XML syntax
        assert 'roles="ADMIN"' not in content.replace('R&amp;D"', '')  # no stray extra roles=""
        assert "&quot;" in content or "&#34;" in content or '\\"' not in content
        # round-trip through a real XML parser to make sure it's well-formed
        import xmltodict
        parsed = xmltodict.parse(f"<users>{content}</users>", force_list=("user",))
        usernames = [u["@username"] for u in parsed["users"]["user"]]
        assert 'mallory" roles="ADMIN' in usernames


class TestGetPrivateDatasetRoles:
    def _write_dataset(self, xmldir, dataset_id, accessible_to=None, title=None, empty_add_attributes=False):
        if empty_add_attributes:
            add_attrs = "<addAttributes></addAttributes>"
        elif title:
            add_attrs = f'<addAttributes><att name="title">{title}</att></addAttributes>'
        else:
            add_attrs = "<addAttributes><att name=\"institution\">Test</att></addAttributes>"

        accessible_to_tag = f"<accessibleTo>{accessible_to}</accessibleTo>" if accessible_to else ""
        xml = f"""<dataset type="EDDTableFromAsciiFiles" datasetID="{dataset_id}" active="true">
  {accessible_to_tag}
  {add_attrs}
</dataset>
"""
        (xmldir / f"{dataset_id}.xml").write_text(xml)

    def test_lists_role_and_title_for_private_dataset(self, tmp_path):
        self._write_dataset(tmp_path, "ds1", accessible_to="PRIVATE_ds1", title="My Dataset")
        with patch.object(utils, "xmldir", str(tmp_path)):
            roles = utils.get_private_dataset_roles()

        assert roles == [{"role": "PRIVATE_ds1", "dataset_id": "ds1", "title": "My Dataset"}]

    def test_excludes_admin_role(self, tmp_path):
        self._write_dataset(tmp_path, "ds1", accessible_to="PRIVATE_ds1,ADMIN", title="My Dataset")
        with patch.object(utils, "xmldir", str(tmp_path)):
            roles = utils.get_private_dataset_roles()

        role_names = [r["role"] for r in roles]
        assert "ADMIN" not in role_names
        assert "PRIVATE_ds1" in role_names

    def test_skips_public_datasets(self, tmp_path):
        self._write_dataset(tmp_path, "ds1", accessible_to=None, title="Public Dataset")
        with patch.object(utils, "xmldir", str(tmp_path)):
            roles = utils.get_private_dataset_roles()

        assert roles == []

    def test_falls_back_to_dataset_id_when_no_title(self, tmp_path):
        self._write_dataset(tmp_path, "ds1", accessible_to="PRIVATE_ds1")
        with patch.object(utils, "xmldir", str(tmp_path)):
            roles = utils.get_private_dataset_roles()

        assert roles[0]["title"] == "ds1"

    def test_empty_addattributes_does_not_crash_or_drop_the_dataset(self, tmp_path):
        # regression test: xmltodict parses an empty <addAttributes/> to None
        # (not {}), so dataset.get('addAttributes', {}) used to return None
        # and .get('att') on it raised, silently dropping the whole dataset
        # (including its accessibleTo role) from the results
        self._write_dataset(tmp_path, "ds1", accessible_to="PRIVATE_ds1", empty_add_attributes=True)
        with patch.object(utils, "xmldir", str(tmp_path)):
            roles = utils.get_private_dataset_roles()

        assert len(roles) == 1
        assert roles[0]["role"] == "PRIVATE_ds1"
        assert roles[0]["title"] == "ds1"  # falls back since there's no title attribute
