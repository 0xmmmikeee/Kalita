// SPDX-License-Identifier: MIT
pragma solidity 0.8.26;

import {Script, console2} from "forge-std/Script.sol";
import {KalitaRegistry} from "../src/KalitaRegistry.sol";

/// Testnet:  forge script script/Deploy.s.sol --rpc-url robinhood_testnet --account kalita-deployer --broadcast
/// Mainnet:  forge script script/Deploy.s.sol --rpc-url robinhood --account kalita-deployer --broadcast
/// Then register the two lists (owner = deployer) and allow the VPS publisher key:
///   cast send $REG "registerList(string,bytes32)" fast   $(cast keccak "kalita-rules-v1-fast")   --rpc-url robinhood_testnet --account kalita-deployer
///   cast send $REG "registerList(string,bytes32)" picker $(cast keccak "kalita-rules-v1-picker") --rpc-url robinhood_testnet --account kalita-deployer
///   cast send $REG "setPublisher(uint256,address,bool)" 0 $PUBLISHER true --rpc-url robinhood_testnet --account kalita-deployer
contract Deploy is Script {
    function run() external returns (KalitaRegistry reg) {
        vm.startBroadcast();
        reg = new KalitaRegistry();
        vm.stopBroadcast();
        console2.log("KalitaRegistry deployed at", address(reg));
    }
}
