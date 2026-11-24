/**
 * 数据根解析：R1 = 家目录下的 .zcode（永远存在），R2 = 自定义数据存储路径下的 .zcode（仅当设置了且 ≠ 家目录）。
 * 路径来源由调用方注入（desktop host 传 homedir 与 getDataBaseDir），模块内不读环境变量。
 */
import { join, resolve } from "node:path";
import type { RootsResolverPort } from "../app/ports.js";
import type { StorageRootSpec } from "@zcode/shared";
import { getProductHomeDataDirName } from "../../paths.js";

/** @deprecated 使用 getProductHomeDataDirName()；保留该常量仅为旧测试/调用方兼容。 */
export const ZCODE_DATA_DIR_NAME = ".zcode";

export function resolveStorageRoots(params: {
  homeDir: string;
  dataBaseDir: string;
  dataDirName?: string;
}): StorageRootSpec[] {
  const dirName = params.dataDirName ?? getProductHomeDataDirName();
  const home = resolve(params.homeDir);
  const dataBase = resolve(params.dataBaseDir);
  const hasCustomDataBaseDir = dataBase !== home;
  const roots: StorageRootSpec[] = [
    { id: "home", path: join(home, dirName), hasCustomDataBaseDir },
  ];
  if (hasCustomDataBaseDir) {
    roots.push({
      id: "dataBaseDir",
      path: join(dataBase, dirName),
      hasCustomDataBaseDir,
    });
  }
  return roots;
}

export function createStorageRootsResolver(params: {
  getHomeDir: () => string;
  getDataBaseDir: () => string;
}): RootsResolverPort {
  return {
    resolveRoots: async () =>
      resolveStorageRoots({ homeDir: params.getHomeDir(), dataBaseDir: params.getDataBaseDir() }),
  };
}
