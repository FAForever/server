#! /bin/bash
docker exec -i faf-db mysql faf < test-data.sql && scripts/run_tests_with_coverage.sh $@
