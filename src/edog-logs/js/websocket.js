/**
 * EDOG Real-Time Log Viewer - WebSocket Manager
 */

// ===== WEBSOCKET MANAGER =====

class WebSocketManager {
  constructor() {
    this.ws = null;
    this.reconnectDelay = 1000; // Start with 1 second
    this.maxReconnectDelay = 30000; // Max 30 seconds
    this.reconnectAttempts = 0;
    this.status = 'disconnected';
    this.onStatusChange = null;
    this.onMessage = null;
    this.url = 'ws://localhost:5555/ws/logs';
  }
  
  connect = () => {
    try {
      this.ws = new WebSocket(this.url);
      this.setStatus('connecting');
      
      this.ws.onopen = () => {
        console.log('WebSocket connected');
        this.setStatus('connected');
        this.reconnectDelay = 1000; // Reset delay on successful connection
        this.reconnectAttempts = 0;
      };
      
      this.ws.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data);
          if (this.onMessage) {
            this.onMessage(message.type, message.data);
          }
        } catch (error) {
          console.error('Failed to parse WebSocket message:', error);
        }
      };
      
      this.ws.onclose = () => {
        console.log('WebSocket closed');
        this.setStatus('disconnected');
        this.scheduleReconnect();
      };
      
      this.ws.onerror = (error) => {
        console.error('WebSocket error:', error);
        this.setStatus('disconnected');
      };
      
    } catch (error) {
      console.error('Failed to create WebSocket:', error);
      this.setStatus('disconnected');
      this.scheduleReconnect();
    }
  }
  
  scheduleReconnect = () => {
    this.reconnectAttempts++;
    const delay = Math.min(this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1), this.maxReconnectDelay);
    
    console.log(`Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts})`);
    this.setStatus('reconnecting');
    
    setTimeout(() => {
      this.connect();
    }, delay);
  }
  
  setStatus = (status) => {
    this.status = status;
    if (this.onStatusChange) {
      this.onStatusChange(status);
    }
  }
  
  disconnect = () => {
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
  }
}
