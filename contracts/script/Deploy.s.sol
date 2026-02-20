// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import {Script} from "forge-std/Script.sol";
import {DailyHeadline} from "../src/DailyHeadline.sol";

contract DeployScript is Script {
    function run() external {
        // Retrieve the private key from your .env
        uint256 deployerPrivateKey = vm.envUint("PRIVATE_KEY");

        vm.startBroadcast(deployerPrivateKey);

        // Deploy the contract
        DailyHeadline nft = new DailyHeadline(vm.addr(deployerPrivateKey));

        nft.mint();

        vm.stopBroadcast();
    }
}