terraform {
  backend "s3" {
    bucket = "acme-tfstate"
    key    = "prod/terraform.tfstate"
    region = "us-east-1"
  }
}

resource "aws_db_instance" "primary" {
  identifier              = "acme-prod"
  engine                  = "postgres"
  engine_version          = "15.5"
  instance_class          = "db.m5.large"
  allocated_storage       = 200
  multi_az                = false
  backup_retention_period = 3
  publicly_accessible     = false
  skip_final_snapshot     = false
}

resource "aws_ecs_service" "api" {
  name          = "acme-api"
  desired_count = 3
}
