#include <TFile.h>
#include <TTree.h>
#include <TRandom.h>
#include <iostream>
#include <string>

void execute_sentinel_ingestion() {
    // Initialize the ROOT binary file in RECREATE mode
    TFile *output_file = new TFile("data/sentinel_capture.root", "RECREATE");

    // Initialize the TTree data structure
    TTree *tree = new TTree("SentinelTree", "K3s Edge Swarm Packet Capture");

    // Define the memory variables for packet metadata
    UInt_t src_ip[4];
    UInt_t dest_ip[4];
    Int_t dest_port;
    Int_t payload_size;
    Double_t timestamp;

    // Map the memory addresses to TTree Branches
    // The strings (e.g., "src_ip[4]/i") strictly define the data types for ROOT's internal byte alignment.
    tree->Branch("src_ip", src_ip, "src_ip[4]/i");
    tree->Branch("dest_ip", dest_ip, "dest_ip[4]/i");
    tree->Branch("dest_port", &dest_port, "dest_port/I");
    tree->Branch("payload_size", &payload_size, "payload_size/I");
    tree->Branch("timestamp", &timestamp, "timestamp/D");

    std::cout << "[SENTINEL] TTree memory mapping complete. Initiating high-speed ingestion loop..." << std::endl;

    // Simulate 100,000 packets of mesh traffic
    for (int i = 0; i < 100000; i++) {
        // Simulate Tailscale 100.x.x.x internal routing
        src_ip[0] = 100;
        src_ip[1] = 64 + (gRandom->Integer(63)); // 100.64.0.0 to 100.127.255.255
        src_ip[2] = gRandom->Integer(255);
        src_ip[3] = gRandom->Integer(255);

        dest_ip[0] = 100;
        dest_ip[1] = gRandom->Integer(127);
        dest_ip[2] = gRandom->Integer(255);
        dest_ip[3] = gRandom->Integer(255);

        dest_port = 1024 + gRandom->Integer(60000);
        payload_size = 64 + gRandom->Integer(1436); // standard MTU simulation
        timestamp = 1723000000.0 + (i * 0.001); // Millisecond precision

        // Execute the write. ROOT pulls directly from the bound memory addresses.
        tree->Fill();
    }

    // Serialize to disk and clear memory
    tree->Write();
    output_file->Close();

    std::cout << "[SENTINEL] 100,000 packets successfully serialized to data/sentinel_capture.root" << std::endl;
}

int main() {
    execute_sentinel_ingestion();
    return 0;
}
