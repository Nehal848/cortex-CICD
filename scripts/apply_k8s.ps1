<#
.SYNOPSIS
Deploys Cortex CI/CD manifests to the local Kubernetes cluster.
.DESCRIPTION
This script applies the RBAC roles and Deployments for Cortex in Minikube/Docker Desktop.
#>

$ErrorActionPreference = "Stop"

Write-Host "Applying Cortex CI/CD Kubernetes manifests..." -ForegroundColor Cyan

# Check if kubectl is installed
if (!(Get-Command "kubectl" -ErrorAction SilentlyContinue)) {
    Write-Host "Error: kubectl is not installed or not in PATH." -ForegroundColor Red
    exit 1
}

# Apply RBAC (so the Cortex API has permission to restart pods for healing)
Write-Host "Applying RBAC..." -ForegroundColor Yellow
kubectl apply -f ..\kubernetes\healing-rbac.yaml

# Apply Deployment
Write-Host "Applying Deployment..." -ForegroundColor Yellow
kubectl apply -f ..\kubernetes\deployment.yaml

Write-Host "Deployment successful! Checking status:" -ForegroundColor Green
kubectl get pods
