#!/bin/bash

# List and remove containers that have been running for more than 1 hour
docker ps -a --filter "ancestor=happysixd/osworld-docker" --format "{{.ID}} {{.CreatedAt}}" | 
while read -r container_id created_at; do
    # Convert creation time to Unix timestamp
    created_timestamp=$(date -d "$(echo $created_at | awk '{print $1" "$2" "$3}')" +%s 2>/dev/null)
    
    # Check if the date conversion was successful
    if [ -z "$created_timestamp" ]; then
        echo "Failed to parse date for container $container_id"
        continue
    fi

    current_timestamp=$(date +%s)
    
    # Calculate time difference in minutes (60 seconds = 1 minute)
    time_diff=$((($current_timestamp - $created_timestamp) / 60))
    echo "Container $container_id has been running for $time_diff minutes"
    # Remove container if it's older than 10 minutes
    # if [ $time_diff -gt 7 ]; then
    docker rm -f "$container_id"
    #fi
done