#!/bin/bash

search_dir=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
parts_dir="${search_dir}/active"

# <user> entries for ERDDAP's "custom" authentication, managed via the CMS
# (see utils.write_erddap_users_xml) - may not exist yet on a fresh deploy.
users_file="${search_dir}/users.xml"
[ -f "$users_file" ] || touch "$users_file"

filenames="${search_dir}/start.xml ${users_file}"

if [ ! -z "$( ls -A $parts_dir )" ]; then
  for entry in "$parts_dir"/*
  do
    filenames="${filenames} ${entry}"
  done  
fi

filenames="${filenames} ${search_dir}/end.xml"

echo $filenames

echo "Ricordati di lasciare due a capo alla fine di ogni file!"

cat $filenames > /usr/local/tomcat/content/erddap/datasets.xml