docker exec -it \
  isp-erddap-cms \
  bash -c "cd /erddapData/hardFlag && touch $1"