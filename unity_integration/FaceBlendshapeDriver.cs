using UnityEngine;

/// <summary>
/// 虚拟人面部表情 Blendshape 驱动器
/// 接收并应用 Python 端传来的 JawOpen, Smile, EyeBlink 等表情权重到 3D 模型的 SkinnedMeshRenderer。
/// </summary>
public class FaceBlendshapeDriver : MonoBehaviour
{
    [Header("Mocap Data Source")]
    public UDPReceiver receiver;

    [Header("Target Mesh")]
    public SkinnedMeshRenderer targetMesh;

    [Header("Blendshape Mapping (输入模型对应的 Blendshape 名字)")]
    public string jawOpenBlendshape = "JawOpen";
    public string smileBlendshape = "Smile";
    public string eyeBlinkLeftBlendshape = "EyeBlinkLeft";
    public string eyeBlinkRightBlendshape = "EyeBlinkRight";

    [Header("Settings")]
    public float blendshapeScale = 100f; // Unity 的 Blendshape 范围通常是 0-100，部分软件可能是 0-1
    public float smoothingSpeed = 15f;   // 引擎端额外的插值平滑速度

    // 内部存储的当前平滑权重
    private float curJawOpen = 0f;
    private float curSmile = 0f;
    private float curBlinkLeft = 0f;
    private float curBlinkRight = 0f;

    // 缓存索引以提升性能
    private int idxJawOpen = -1;
    private int idxSmile = -1;
    private int idxBlinkLeft = -1;
    private int idxBlinkRight = -1;

    void Start()
    {
        if (targetMesh == null)
        {
            targetMesh = GetComponentInChildren<SkinnedMeshRenderer>();
        }

        if (targetMesh != null)
        {
            idxJawOpen = targetMesh.sharedMesh.GetBlendShapeIndex(jawOpenBlendshape);
            idxSmile = targetMesh.sharedMesh.GetBlendShapeIndex(smileBlendshape);
            idxBlinkLeft = targetMesh.sharedMesh.GetBlendShapeIndex(eyeBlinkLeftBlendshape);
            idxBlinkRight = targetMesh.sharedMesh.GetBlendShapeIndex(eyeBlinkRightBlendshape);

            if (idxJawOpen == -1 && idxSmile == -1)
            {
                Debug.LogWarning("[Mocap Face] 未能在目标 Mesh 上找到对应的 Blendshape 名称，请检查模型是否有这些表情！");
            }
        }
    }

    void Update()
    {
        if (receiver == null || targetMesh == null) return;

        BlendshapesData data = receiver.GetCurrentBlendshapes();
        if (data == null) return;

        // 1. 平滑过渡 (Lerp)
        // 虽然 Python 端已经用 1€ Filter 平滑过了，但在 Unity 引擎里加一层平滑可以让高帧率下过渡更丝滑
        curJawOpen = Mathf.Lerp(curJawOpen, data.JawOpen * blendshapeScale, Time.deltaTime * smoothingSpeed);
        curSmile = Mathf.Lerp(curSmile, data.Smile * blendshapeScale, Time.deltaTime * smoothingSpeed);
        curBlinkLeft = Mathf.Lerp(curBlinkLeft, data.EyeBlinkLeft * blendshapeScale, Time.deltaTime * smoothingSpeed);
        curBlinkRight = Mathf.Lerp(curBlinkRight, data.EyeBlinkRight * blendshapeScale, Time.deltaTime * smoothingSpeed);

        // 2. 应用权重
        if (idxJawOpen != -1) targetMesh.SetBlendShapeWeight(idxJawOpen, curJawOpen);
        if (idxSmile != -1) targetMesh.SetBlendShapeWeight(idxSmile, curSmile);
        if (idxBlinkLeft != -1) targetMesh.SetBlendShapeWeight(idxBlinkLeft, curBlinkLeft);
        if (idxBlinkRight != -1) targetMesh.SetBlendShapeWeight(idxBlinkRight, curBlinkRight);
    }
}
