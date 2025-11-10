#!/usr/bin/env python3
"""
Script to remove Docker containers based on their age.
This script lists and removes containers from the 'happysixd/osworld-docker' image
that have been running for more than a specified time period.
"""

import docker
import sys
import argparse
from datetime import datetime, timezone
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description='Remove old Docker containers from happysixd/osworld-docker image'
    )
    parser.add_argument(
        '--min-age',
        type=int,
        default=0,
        help='Minimum age in minutes before removing containers (default: 0, removes all)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be removed without actually removing'
    )
    parser.add_argument(
        '--image',
        type=str,
        default='happysixd/osworld-docker',
        help='Docker image name to filter containers (default: happysixd/osworld-docker)'
    )
    return parser.parse_args()


def get_container_age_minutes(container):
    """
    Calculate the age of a container in minutes.
    
    Args:
        container: Docker container object
        
    Returns:
        int: Age in minutes, or None if calculation fails
    """
    try:
        # Get container creation time
        created_str = container.attrs['Created']
        
        # Parse the ISO 8601 timestamp
        # Docker returns timestamps like: "2024-01-10T12:34:56.789012345Z"
        created_dt = datetime.fromisoformat(created_str.replace('Z', '+00:00'))
        
        # Get current time in UTC
        now = datetime.now(timezone.utc)
        
        # Calculate age in minutes
        age_seconds = (now - created_dt).total_seconds()
        age_minutes = int(age_seconds / 60)
        
        return age_minutes
    except Exception as e:
        logger.error(f"Failed to calculate age for container {container.id[:12]}: {e}")
        return None


def remove_old_containers(image_name, min_age_minutes=0, dry_run=False):
    """
    Remove containers from specified image that are older than min_age_minutes.
    
    Args:
        image_name: Name of the Docker image to filter
        min_age_minutes: Minimum age in minutes before removing
        dry_run: If True, only show what would be removed
        
    Returns:
        tuple: (removed_count, failed_count)
    """
    try:
        client = docker.from_env()
    except Exception as e:
        logger.error(f"Failed to connect to Docker: {e}")
        logger.error("Make sure Docker is running and you have permission to access it")
        return 0, 0
    
    removed_count = 0
    failed_count = 0
    
    try:
        # Get all containers (including stopped ones)
        all_containers = client.containers.list(all=True)
        
        # Filter containers by image
        matching_containers = []
        for container in all_containers:
            try:
                # Check if container's image matches
                image_tags = container.image.tags if container.image else []
                if any(image_name in tag for tag in image_tags):
                    matching_containers.append(container)
            except Exception as e:
                logger.warning(f"Failed to check image for container {container.id[:12]}: {e}")
                continue
        
        if not matching_containers:
            logger.info(f"No containers found for image '{image_name}'")
            return 0, 0
        
        logger.info(f"Found {len(matching_containers)} container(s) for image '{image_name}'")
        
        # Process each matching container
        for container in matching_containers:
            try:
                container_id = container.id[:12]
                age_minutes = get_container_age_minutes(container)
                
                if age_minutes is None:
                    logger.warning(f"Skipping container {container_id} due to age calculation failure")
                    failed_count += 1
                    continue
                
                logger.info(f"Container {container_id} has been running for {age_minutes} minutes")
                
                # Check if container is old enough to remove
                if age_minutes >= min_age_minutes:
                    if dry_run:
                        logger.info(f"[DRY RUN] Would remove container {container_id}")
                        removed_count += 1
                    else:
                        try:
                            container.remove(force=True)
                            logger.info(f"Successfully removed container {container_id}")
                            removed_count += 1
                        except Exception as e:
                            logger.error(f"Failed to remove container {container_id}: {e}")
                            failed_count += 1
                else:
                    logger.info(f"Container {container_id} is too young to remove (age: {age_minutes} min, threshold: {min_age_minutes} min)")
                    
            except Exception as e:
                logger.error(f"Error processing container: {e}")
                failed_count += 1
                continue
        
    except Exception as e:
        logger.error(f"Error listing containers: {e}")
        return removed_count, failed_count
    
    return removed_count, failed_count


def main():
    """Main entry point."""
    args = parse_args()
    
    logger.info("=" * 60)
    logger.info("Docker Container Cleanup Script")
    logger.info("=" * 60)
    logger.info(f"Image filter: {args.image}")
    logger.info(f"Minimum age: {args.min_age} minutes")
    logger.info(f"Dry run: {args.dry_run}")
    logger.info("=" * 60)
    
    removed, failed = remove_old_containers(
        image_name=args.image,
        min_age_minutes=args.min_age,
        dry_run=args.dry_run
    )
    
    logger.info("=" * 60)
    logger.info("Summary:")
    logger.info(f"  Containers removed: {removed}")
    logger.info(f"  Failures: {failed}")
    logger.info("=" * 60)
    
    # Exit with error code if there were failures
    if failed > 0:
        sys.exit(1)
    
    sys.exit(0)


if __name__ == '__main__':
    main()
