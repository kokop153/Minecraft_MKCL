
import json
import os
import sys

def generate_launch_script(minecraft_dir, version, java_path, max_memory="4G", username="Player"):
    """
    生成Minecraft启动脚本
    :param minecraft_dir: .minecraft文件夹路径
    :param version: 游戏版本号 (例如 '1.20.1')
    :param java_path: java.exe的完整路径
    :param max_memory: 最大内存分配 (例如 '4G')
    :param username: 玩家昵称
    :return: 生成的.bat文件内容
    """
    version_dir = os.path.join(minecraft_dir, "versions", version)
    json_path = os.path.join(version_dir, f"{version}.json")
    
    if not os.path.exists(json_path):
        raise FileNotFoundError(f"未找到版本JSON文件: {json_path}")

    with open(json_path, 'r', encoding='utf-8') as f:
        version_data = json.load(f)

    # 1. 构建类路径 (Classpath)
    libraries_dir = os.path.join(minecraft_dir, "libraries")
    classpath_entries = []
    
    # 添加版本jar本身
    version_jar = os.path.join(version_dir, f"{version}.jar")
    if os.path.exists(version_jar):
        classpath_entries.append(version_jar)

    # 添加依赖库
    for lib in version_data.get("libraries", []):
        if "downloads" in lib and "artifact" in lib["downloads"]:
            path = lib["downloads"]["artifact"]["path"]
            full_path = os.path.join(libraries_dir, path)
            if os.path.exists(full_path):
                classpath_entries.append(full_path)
    
    # Windows使用分号分隔类路径
    classpath_str = ";".join(classpath_entries)

    # 2. 获取主类
    main_class = version_data.get("mainClass", "net.minecraft.client.main.Main")

    # 3. 构建JVM参数
    jvm_args = [
        f"-Xmx{max_memory}",
        f"-Xms{max_memory}",
        "-XX:+UseG1GC",
        "-XX:+ParallelRefProcEnabled",
        "-XX:MaxGCPauseMillis=200",
        "-XX:+UnlockExperimentalVMOptions",
        "-XX:+DisableExplicitGC",
        "-XX:+AlwaysPreTouch",
        "-Dfml.ignoreInvalidMinecraftCertificates=True",
        "-Dfml.ignorePatchDiscrepancies=True",
        f"-Djava.library.path={os.path.join(version_dir, f'{version}-natives')}"
    ]

    # 4. 构建游戏参数 (简化版，实际需根据version.json的arguments字段解析)
    game_args = [
        "--username", username,
        "--version", version,
        "--gameDir", minecraft_dir,
        "--assetsDir", os.path.join(minecraft_dir, "assets"),
        "--assetIndex", version_data.get("assetIndex", {}).get("id", version),
        "--uuid", "00000000-0000-0000-0000-000000000000", # 离线模式示例
        "--accessToken", "0",
        "--userType", "legacy"
    ]

    # 5. 生成Bat脚本内容
    bat_content = "@echo off\n"
    bat_content += f"title Minecraft {version}\n"
    bat_content += f"cd /d \"{minecraft_dir}\"\n"
    bat_content += f"\"{java_path}\" ^\n"
    bat_content += " ".join(jvm_args) + " ^\n"
    bat_content += f"-cp \"{classpath_str}\" ^\n"
    bat_content += f"{main_class} ^\n"
    bat_content += " ".join(game_args) + "\n"
    bat_content += "pause\n"

    return bat_content

if __name__ == "__main__":
    # 配置区域 - 请根据实际情况修改
    MC_DIR = r"C:\Users\YourName\AppData\Roaming\.minecraft"
    VERSION = "1.20.1"
    JAVA_EXE = r"C:\Program Files\Java\jdk-17\bin\java.exe"
    
    try:
        script_content = generate_launch_script(MC_DIR, VERSION, JAVA_EXE)
        output_file = os.path.join(MC_DIR, f"start_{VERSION}.bat")
        with open(output_file, 'w', encoding='gbk') as f:
            f.write(script_content)
        print(f"启动脚本已生成: {output_file}")
    except Exception as e:
        print(f"生成失败: {e}")
