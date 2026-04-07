using System;
using System.Net;
using System.Net.Sockets;
using System.Text;
using System.Threading;
using System.Collections.Generic;
using UnityEngine;

// 1. 定义与 Python 端匹配的数据结构
[Serializable]
public class HeadPose
{
    public float pitch;
    public float yaw;
    public float roll;
}

[Serializable]
public class LandmarkWrapper
{
    public List<Landmark> pose;
    public List<Landmark> face;
    public List<Landmark> left_hand;
    public List<Landmark> right_hand;
    public HeadPose head_pose; // 接收高精度头部欧拉角
}

public class UDPReceiver : MonoBehaviour
{
    [Header("UDP Configuration")]
    public int listenPort = 7001;

    [Header("Visualization")]
    public float scaleFactor = 1.0f; // 缩放骨骼比例
    public bool drawBones = true;    // 是否绘制连线
    public GameObject jointPrefab;   // 用于可视化关节点的小球预制体

    private UdpClient udpClient;
    private Thread receiveThread;
    private bool isRunning = false;
    private string lastReceivedData = "";

    // 存储最新反序列化后的数据
    private Landmark[] currentLandmarks = new Landmark[33];
    private HeadPose currentHeadPose = null;
    private bool hasNewData = false;

    // 提供给外部脚本访问的 API
    public Landmark[] GetCurrentLandmarks() { return currentLandmarks; }
    public HeadPose GetCurrentHeadPose() { return currentHeadPose; }

    // 存储生成的 33 个 Sphere
    private Transform[] jointTransforms = new Transform[33];
    private object dataLock = new object(); // 用于线程同步

    // MediaPipe 骨骼拓扑结构，用于 DrawLine
    private readonly int[,] connections = new int[,]
    {
        {0, 1}, {1, 2}, {2, 3}, {3, 7}, {0, 4}, {4, 5}, {5, 6}, {6, 8},
        {9, 10}, {11, 12}, {11, 13}, {13, 15}, {15, 17}, {15, 19}, {15, 21}, {17, 19},
        {12, 14}, {14, 16}, {16, 18}, {16, 20}, {16, 22}, {18, 20},
        {11, 23}, {12, 24}, {23, 24}, {23, 25}, {24, 26}, {25, 27}, {26, 28},
        {27, 29}, {28, 30}, {29, 31}, {30, 32}, {27, 31}, {28, 32}
    };

    void Start()
    {
        // 1. 初始化 33 个关节点的小球
        for (int i = 0; i < 33; i++)
        {
            GameObject joint = null;
            if (jointPrefab != null)
            {
                joint = Instantiate(jointPrefab, Vector3.zero, Quaternion.identity);
            }
            else
            {
                // 如果没有预制体，创建简单的红色小球
                joint = GameObject.CreatePrimitive(PrimitiveType.Sphere);
                joint.transform.localScale = Vector3.one * 0.05f;
                joint.GetComponent<Renderer>().material.color = Color.red;
                Destroy(joint.GetComponent<Collider>());
            }
            joint.name = "Joint_" + i;
            joint.transform.parent = this.transform; // 设置当前物体为父物体
            jointTransforms[i] = joint.transform;
        }

        // 2. 启动 UDP 监听线程
        StartReceiving();
    }

    private void StartReceiving()
    {
        isRunning = true;
        receiveThread = new Thread(new ThreadStart(ReceiveData));
        receiveThread.IsBackground = true;
        receiveThread.Start();
        Debug.Log("[Mocap] UDP Listener started on port " + listenPort);
    }

    private void ReceiveData()
    {
        try
        {
            udpClient = new UdpClient(listenPort);
            IPEndPoint anyIP = new IPEndPoint(IPAddress.Any, 0);

            while (isRunning)
            {
                // 阻塞等待数据
                byte[] data = udpClient.Receive(ref anyIP);
                string text = Encoding.UTF8.GetString(data);

                // 解析 JSON 数据并更新共享状态 (加锁)
                try
                {
                    LandmarkWrapper wrapper = JsonUtility.FromJson<LandmarkWrapper>(text);
                    if (wrapper != null && wrapper.pose != null && wrapper.pose.Count == 33)
                    {
                        lock (dataLock)
                        {
                            for (int i = 0; i < 33; i++)
                            {
                                currentLandmarks[i] = wrapper.pose[i];
                            }
                            hasNewData = true;

                            // 此时我们成功反序列化了脸部和手部的数据
                            // int faceNodes = wrapper.face != null ? wrapper.face.Count : 0;
                            // Debug.Log($"[Mocap] Received Pose:33 Face:{faceNodes}");
                        }
                    }
                }
                catch (Exception jsonEx)
                {
                    Debug.LogWarning("[Mocap] JSON Parse error: " + jsonEx.Message);
                }
            }
        }
        catch (Exception err)
        {
            if (isRunning) // 过滤正常退出时的异常
            {
                Debug.LogError("[Mocap] UDP Receive error: " + err.Message);
            }
        }
    }

    void Update()
    {
        // 从后台线程安全读取最新的位置数据
        lock (dataLock)
        {
            if (hasNewData)
            {
                // 更新 33 个关节点的位置
                for (int i = 0; i < 33; i++)
                {
                    Landmark lm = currentLandmarks[i];
                    if (lm != null)
                    {
                        // 组装新的局部坐标 (这里假设发送端已经通过 flip 参数处理好了方向)
                        // 注意：MediaPipe 出来的尺寸通常是以米为单位 (例如肩宽约 0.4 米)
                        Vector3 newPos = new Vector3(lm.x, lm.y, lm.z) * scaleFactor;

                        // 由于受到父级物体变换的影响，直接赋值 localPosition
                        jointTransforms[i].localPosition = newPos;

                        // 可见度过滤（如果某个点完全被遮挡可以隐藏它，但 1€ 滤波器通常会保持位置）
                        jointTransforms[i].gameObject.SetActive(lm.visibility > 0.5f);
                    }
                }
                hasNewData = false;
            }
        }

        // 绘制骨架连线 (Scene 视图可见，或在 Game 视图开启 Gizmos)
        if (drawBones)
        {
            for (int i = 0; i < connections.GetLength(0); i++)
            {
                int startIdx = connections[i, 0];
                int endIdx = connections[i, 1];

                if (jointTransforms[startIdx].gameObject.activeSelf && jointTransforms[endIdx].gameObject.activeSelf)
                {
                    // 使用 Debug.DrawLine 连接物理世界空间的两点
                    Debug.DrawLine(jointTransforms[startIdx].position, jointTransforms[endIdx].position, Color.cyan);
                }
            }
        }
    }

    void OnDestroy()
    {
        // 清理线程和 Socket
        isRunning = false;
        if (udpClient != null)
        {
            udpClient.Close();
        }
        if (receiveThread != null && receiveThread.IsAlive)
        {
            receiveThread.Abort();
        }
    }
}
