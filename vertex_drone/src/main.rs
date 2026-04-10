use std::collections::{HashMap, HashSet};
use std::env;
use std::sync::Arc;
use std::time::{Duration, Instant};
use tokio::net::UdpSocket;
use tokio::sync::Mutex;
use serde::{Deserialize, Serialize};
use rand::thread_rng;
use rand::seq::SliceRandom;

#[derive(Debug, Clone, Serialize, Deserialize)]
enum DroneState {
    READY,
    CLAIMING,
    SEARCHING,
    COMPLETE,
    OFFLINE
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct Position {
    x: i32,
    y: i32,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "type")]
enum Message {
    HELLO {
        drone_id: String,
        timestamp_ms: u64,
        status: String,
    },
    HEARTBEAT {
        drone_id: String,
        timestamp_ms: u64,
        position: Position,
        sectors_claimed: Vec<String>,
        sectors_searched: Vec<String>,
        status: String,
    },
    CLAIM {
        drone_id: String,
        sector: String,
        timestamp_ms: u64,
        priority: f32,
    },
    RELEASE {
        releasing_drone: String,
        dead_drone: String,
        sectors_released: Vec<String>,
        timestamp_ms: u64,
    },
    HAZARD {
        sector: String,
        timestamp_ms: u64,
    },
    SYSTEM {
        action: String,
        timestamp_ms: u64,
    }
}

const BIND_ADDR: &str = "0.0.0.0:1883";
// We broadcast locally so Python UI and other rust nodes can sniff
const BROADCAST_ADDR: &str = "255.255.255.255:1883";

struct Drone {
    node_id: String,
    state: DroneState,
    current_pos: Position,
    peers: HashMap<String, Instant>,
    claimed_sectors: HashSet<String>,
    searched_sectors: HashSet<String>,
    global_searched: HashSet<String>,
    all_claims: HashMap<String, String>,
    known_hazards: HashSet<String>,
    ready_since: Option<Instant>,
    grid_x: i32,
    grid_y: i32,
    total_sectors: usize,
}

impl Drone {
    fn new(node_id: String, grid_x: i32, grid_y: i32) -> Self {
        use rand::Rng;
        let mut rng = thread_rng();
        // Spawn randomly within a staging hub near the center
        let hub_x = grid_x / 2;
        let hub_y = grid_y / 2;
        let start_x = rng.gen_range(hub_x.saturating_sub(1)..=hub_x.saturating_add(1));
        let start_y = rng.gen_range(hub_y.saturating_sub(1)..=hub_y.saturating_add(1));

        Self {
            node_id,
            state: DroneState::READY,
            current_pos: Position { x: start_x, y: start_y }, // Deployment Hub Cluster

            peers: HashMap::new(),
            claimed_sectors: HashSet::new(),
            searched_sectors: HashSet::new(),
            global_searched: HashSet::new(),
            all_claims: HashMap::new(),
            known_hazards: HashSet::new(),
            ready_since: None,
            grid_x,
            grid_y,
            total_sectors: (grid_x * grid_y) as usize,
        }
    }
}

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<String> = env::args().collect();
    let mut node_id = format!("drone_{}", rand::random::<u16>());
    let mut grid_x = 10;
    let mut grid_y = 10;

    let mut i = 1;
    while i < args.len() {
        if args[i] == "--id" && i + 1 < args.len() {
            node_id = args[i+1].clone();
            i += 2;
        } else if args[i] == "--grid" && i + 2 < args.len() {
            grid_x = args[i+1].parse().unwrap_or(10);
            grid_y = args[i+2].parse().unwrap_or(10);
            i += 3;
        } else {
            i += 1;
        }
    }

    println!("[{}] Booting Vertex Native Mesh Layer...", node_id);

    // UDP Socket for sending broadcasts
    let socket = Arc::new(UdpSocket::bind("0.0.0.0:0").await?);
    socket.set_broadcast(true)?;

    // Shared state
    let drone = Arc::new(Mutex::new(Drone::new(node_id.clone(), grid_x, grid_y)));
    let drone_clone = drone.clone();

    // Receiver socket for listening to UDP broadcasts
    // Need SO_REUSEADDR and SO_REUSEPORT so multiple drones can run locally on port 1883
    let recv_socket = socket2::Socket::new(
        socket2::Domain::IPV4,
        socket2::Type::DGRAM,
        None,
    )?;
    recv_socket.set_reuse_address(true)?;
    #[cfg(unix)]
    recv_socket.set_reuse_port(true)?;
    recv_socket.set_nonblocking(true)?;
    recv_socket.bind(&BIND_ADDR.parse::<std::net::SocketAddr>().unwrap().into())?;
    let recv_socket = UdpSocket::from_std(recv_socket.into())?;
    let recv_socket = Arc::new(recv_socket);

    // Receiver task
    let recv_task = tokio::spawn(async move {
        let mut buf = [0; 65535];
        loop {
            if let Ok((len, _addr)) = recv_socket.recv_from(&mut buf).await {
                if let Ok(msg) = serde_json::from_slice::<Message>(&buf[..len]) {
                    let mut d = drone_clone.lock().await;
                    match msg {
                        Message::HELLO { drone_id, .. } => {
                            if drone_id != d.node_id {
                                d.peers.insert(drone_id.clone(), Instant::now());
                                println!("[{}] Discovered peer via Vertex: {}", d.node_id, drone_id);
                            }
                        }
                        Message::HEARTBEAT { drone_id, sectors_claimed, sectors_searched, .. } => {
                            if drone_id != d.node_id {
                                d.peers.insert(drone_id.clone(), Instant::now());
                                for s in sectors_searched {
                                    d.global_searched.insert(s);
                                }
                                for s in sectors_claimed {
                                    if !d.all_claims.contains_key(&s) {
                                        d.all_claims.insert(s, drone_id.clone());
                                    }
                                }
                            }
                        }
                        Message::CLAIM { drone_id, sector, .. } => {
                            if !d.all_claims.contains_key(&sector) {
                                d.all_claims.insert(sector.clone(), drone_id.clone());
                                if drone_id == d.node_id {
                                    d.claimed_sectors.insert(sector.clone());
                                }
                            } else if drone_id == d.node_id && d.all_claims.get(&sector) != Some(&d.node_id) {
                                println!("[{}] Vertex Consenus Rejected: {} already owned", d.node_id, sector);
                            }
                        }
                        Message::RELEASE { dead_drone, sectors_released, .. } => {
                            d.peers.remove(&dead_drone);
                            for s in sectors_released {
                                if d.all_claims.get(&s) == Some(&dead_drone) {
                                    d.all_claims.remove(&s);
                                    d.claimed_sectors.remove(&s);
                                }
                            }
                        }
                        Message::HAZARD { sector, .. } => {
                            if !d.known_hazards.contains(&sector) {
                                println!("[{}] Vertex Gossip: HAZARD designated at {}", d.node_id, sector);
                                d.known_hazards.insert(sector);
                            }
                        }
                        Message::SYSTEM { action, .. } => {
                            if action == "START" {
                                if matches!(d.state, DroneState::READY) {
                                    println!("[{}] Vertex System: MISSION START received!", d.node_id);
                                    d.state = DroneState::CLAIMING;
                                }
                            }
                        }
                    }
                }
            }
        }
    });

    let send_sock = socket.clone();
    let node_id_clone = node_id.clone();
    
    let hello = Message::HELLO {
        drone_id: node_id_clone.clone(),
        timestamp_ms: 0,
        status: "READY".to_string(),
    };
    let _ = send_sock.send_to(&serde_json::to_vec(&hello)?, BROADCAST_ADDR).await;

    let mut last_hb = Instant::now();

    loop {
        tokio::time::sleep(Duration::from_millis(50)).await;
        let mut d = drone.lock().await;
        let now = Instant::now();

        // Check dead peers
        let mut dead_peers = Vec::new();
        for (peer, last_seen) in d.peers.iter() {
            if now.duration_since(*last_seen) > Duration::from_secs(5) {
                dead_peers.push(peer.clone());
            }
        }
        for dead in dead_peers {
            println!("[{}] DETECTED {} OFFLINE via Vertex timeout", d.node_id, dead);
            let released: Vec<String> = d.all_claims.iter()
                .filter(|(_, owner)| *owner == &dead)
                .map(|(s, _)| s.clone())
                .collect();
                
            let release_msg = Message::RELEASE {
                releasing_drone: d.node_id.clone(),
                dead_drone: dead.clone(),
                sectors_released: released,
                timestamp_ms: 0,
            };
            let _ = send_sock.send_to(&serde_json::to_vec(&release_msg)?, BROADCAST_ADDR).await;
            d.peers.remove(&dead);
        }

        // State Machine
        match d.state {
            DroneState::READY => {
                if d.ready_since.is_none() {
                    d.ready_since = Some(now);
                }
                // We now wait for the SYSTEM START signal rather than counting peers
                // Fallback: if we haven't started after 60s, start anyway for robust testing
                if now.duration_since(d.ready_since.unwrap()) >= Duration::from_secs(60) {
                    println!("[{}] Vertex Warning: 60s timeout elapsed, Auto-Starting!", d.node_id);
                    d.state = DroneState::CLAIMING;
                }
            }
            DroneState::CLAIMING => {
                let mut all_sectors = Vec::new();
                for y in 0..d.grid_y {
                    for x in 0..d.grid_x {
                        all_sectors.push(format!("{}_{}", x, y));
                    }
                }
                all_sectors.shuffle(&mut thread_rng());
                
                for s in all_sectors {
                    if !d.all_claims.contains_key(&s) {
                        let claim_msg = Message::CLAIM {
                            drone_id: d.node_id.clone(),
                            sector: s.clone(),
                            timestamp_ms: 0,
                            priority: 0.5,
                        };
                        let _ = send_sock.send_to(&serde_json::to_vec(&claim_msg)?, BROADCAST_ADDR).await;
                        break; 
                    }
                }
                
                if d.all_claims.len() >= d.total_sectors {
                    d.state = DroneState::SEARCHING;
                }
            }
            DroneState::SEARCHING => {
                let mut to_search: Vec<String> = d.claimed_sectors.iter()
                    .filter(|s| !d.global_searched.contains(*s))
                    .cloned()
                    .collect();
                
                if !to_search.is_empty() {
                    to_search.sort_by(|a, b| {
                        let pa: Vec<&str> = a.split('_').collect();
                        let pb: Vec<&str> = b.split('_').collect();
                        let xa: i32 = pa[0].parse().unwrap();
                        let ya: i32 = pa[1].parse().unwrap();
                        let xb: i32 = pb[0].parse().unwrap();
                        let yb: i32 = pb[1].parse().unwrap();
                        
                        // Greedy pathfinding: Closest node first (Euclidean squared distance)
                        let mut dist_a = (xa - d.current_pos.x).pow(2) + (ya - d.current_pos.y).pow(2);
                        let mut dist_b = (xb - d.current_pos.x).pow(2) + (yb - d.current_pos.y).pow(2);
                        
                        // Aversion Weighting: Inflate distance by massive penalty for hazards to force avoidance
                        if d.known_hazards.contains(a) { dist_a += 10000; }
                        if d.known_hazards.contains(b) { dist_b += 10000; }
                        
                        dist_a.cmp(&dist_b)
                    });
                    
                    let target = to_search[0].clone();
                    
                    // Slow down the search simulation dramatically so the user can easily observe it!
                    let delay = if d.known_hazards.contains(&target) { 
                        4000 // 4 seconds penalty if hazard is present
                    } else { 
                        // Random delay between 800ms and 2000ms for regular sectors
                        use rand::Rng;
                        rand::thread_rng().gen_range(800..=2000)
                    };
                    
                    drop(d);
                    tokio::time::sleep(Duration::from_millis(delay)).await;
                    d = drone.lock().await; // re-acquire lock after sleeping
                    
                    d.searched_sectors.insert(target.clone());
                    d.global_searched.insert(target.clone());
                    
                    let parts: Vec<&str> = target.split('_').collect();
                    d.current_pos = Position { x: parts[0].parse().unwrap(), y: parts[1].parse().unwrap() };
                    println!("[{}] Vertex sector synced: {}", d.node_id, target);
                } else if d.all_claims.len() < d.total_sectors {
                    d.state = DroneState::CLAIMING;
                } else {
                    d.state = DroneState::COMPLETE;
                }
            }
            DroneState::COMPLETE => {
                if d.all_claims.len() < d.total_sectors {
                    d.state = DroneState::CLAIMING;
                }
            }
            _ => {}
        }

        if now.duration_since(last_hb) > Duration::from_secs(1) {
            let hb = Message::HEARTBEAT {
                drone_id: d.node_id.clone(),
                timestamp_ms: 0,
                position: d.current_pos.clone(),
                sectors_claimed: d.claimed_sectors.iter().cloned().collect(),
                sectors_searched: d.searched_sectors.iter().cloned().collect(),
                status: format!("{:?}", d.state),
            };
            let _ = send_sock.send_to(&serde_json::to_vec(&hb)?, BROADCAST_ADDR).await;
            last_hb = now;
        }
    }
}
