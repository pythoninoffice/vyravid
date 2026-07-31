import { Config } from "@remotion/cli/config";
import { webpackOverride } from "./remotion/webpack-override";

Config.setVideoImageFormat("jpeg");
Config.setOverwriteOutput(true);
Config.overrideWebpackConfig(webpackOverride);

// Premium video settings for high quality output
Config.setConcurrency(4);
Config.setJpegQuality(90);
Config.setPixelFormat("yuv420p");
