#!/bin/bash

search_dir=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
parts_dir="${search_dir}/active"

filenames="${search_dir}/start.xml"

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