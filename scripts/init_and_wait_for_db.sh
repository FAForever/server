#!/usr/bin/env bash
pushd db
docker build -t faf-db .
DB_CONTAINER=`docker run -d --name faf-db -e MYSQL_ROOT_PASSWORD=banana faf-db`
until nc -z $(sudo docker inspect --format='{{.NetworkSettings.IPAddress}}' $DB_CONTAINER) 3306
do
  echo "Waiting for mysql container..."
  sleep 0.5
done
docker logs faf-db
docker exec -i faf-db mysql -h127.0.0.1 -uroot -pbanana -e 'create database faf_test;'
docker exec -i faf-db mysql -h127.0.0.1 -uroot -pbanana faf_test < db-structure.sql
docker exec -i faf-db mysql -h127.0.0.1 -uroot -pbanana faf_test < db-data.sql
popd
