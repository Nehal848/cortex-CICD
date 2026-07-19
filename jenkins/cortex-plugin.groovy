def call(Map config) {
    echo "[Cortex] Monitoring step for failures..."
    
    try {
        // Execute the actual pipeline step
        config.step()
    } catch (Exception e) {
        if (config.autoHeal) {
            echo "[Cortex] Failure detected! Extracting context..."
            def logs = currentBuild.rawBuild.getLog(100)
            
            // In a real plugin, this would send an HTTP POST to the Cortex API
            echo "[Cortex] Sending ${logs.size()} lines to AI Healer..."
            echo "[Cortex] Awaiting patch generation..."
            
            // Sleep simulates waiting for AI response
            sleep(time: 10, unit: 'SECONDS')
            
            echo "[Cortex] Received patch. Applying to temporary branch and retrying..."
        }
        throw e
    }
}
